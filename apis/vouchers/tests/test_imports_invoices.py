"""Sales and Credit/Debit Note imports: source references, original entitlement, bills."""

import datetime as dt
import secrets
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT
from pydantic import SecretStr
from sqlalchemy import select
from test_imports_api import auth, rows, validated
from test_imports_money import commit, outcome, upload
from voucher_execution.invoice import InvoiceCalculationDetail

from vouchers.domain.imports import (
    Master,
    OpenBill,
    OriginalInvoice,
    OriginalLine,
    Resolution,
)
from vouchers.models import core as m
from vouchers.models.invoice import VoucherInvoiceDetail
from vouchers.schemas.owners import Owner
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks import imports as tasks
from vouchers.tasks.sources import apply_bundle

TODAY = dt.date.today()


class Book:
    """A customer and a supplier, each with one posted original invoice of two lines."""

    def __init__(self) -> None:
        self.customer, self.supplier = uuid7(), uuid7()
        self.customer_ledger, self.supplier_ledger = uuid7(), uuid7()
        self.income, self.expense = uuid7(), uuid7()
        self.sale, self.purchase = uuid7(), uuid7()
        self.lines = {code: (uuid7(), uuid7()) for code in ("SALES", "PURCHASE")}
        self.sale_bill = OpenBill(uuid7(), "DEBT", "INR", Decimal("1000"))
        self.purchase_bill = OpenBill(uuid7(), "CREDIT", "INR", Decimal("800"))
        self.returnable = True
        self.with_bills = True
        self.previews: list[str] = []

    def original(self, kind: str, source, account, total: str) -> OriginalInvoice:
        first, second = self.lines[kind]
        return OriginalInvoice(
            source, "INR", TODAY - dt.timedelta(days=5), self.returnable,
            (
                OriginalLine(first, 1, account, "SERVICE", True, Decimal(total)),
                OriginalLine(second, 2, account, "ACCOUNT", False, Decimal("50")),
            ),
        )

    def resolution(self) -> Resolution:
        def master(source):
            return Master(source, 1, "ACTIVE")

        return Resolution(
            parties={"CUS-1": master(self.customer), "SUP-1": master(self.supplier)},
            gstin_parties={},
            party_ids={self.customer: master(self.customer), self.supplier: master(self.supplier)},
            party_ledgers={
                self.customer: (("CUS-1-L", master(self.customer_ledger)),),
                self.supplier: (("SUP-1-L", master(self.supplier_ledger)),),
            },
            accounts={"INC": master(self.income), "EXP": master(self.expense)},
            ledger_roles={self.customer_ledger: "CUSTOMER", self.supplier_ledger: "SUPPLIER"},
            bills={
                (self.customer_ledger, "inv-1"): (self.sale_bill,),
                (self.supplier_ledger, "bill-1"): (self.purchase_bill,),
            } if self.with_bills else {},
            invoices={
                ("SALES", self.customer_ledger, "inv-1"):
                    (self.original("SALES", self.sale, self.income, "600"),),
                ("PURCHASE", self.supplier_ledger, "bill-1"):
                    (self.original("PURCHASE", self.purchase, self.expense, "400"),),
            },
        )


@pytest.fixture
async def book(app, monkeypatch) -> Book:
    known = Book()
    owner = Owner(
        owner="accounting", origin="http://127.0.0.1", key_id="invoice-import",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    app.state.settings.master_lookup_owner = app.state.settings.execution_owner = owner
    previews = []

    async def resolve(owner, tenant, company, **codes):
        return known.resolution()

    async def preview(owner, command):
        previews.append(command.kind)
        payable = sum((Decimal(row.amount) for row in command.invoice.supplies), Decimal(0))
        return InvoiceCalculationDetail.model_validate({
            "calculation_hash": "d" * 64, "currency": "INR", "commercial_total": str(payable),
            "tax_total": "0", "charged_tax_total": "0", "rounding": "0",
            "payable": str(payable), "lines": [], "components": [], "allocations": [],
            "tax_evidence": [],
        })

    monkeypatch.setattr(tasks, "default_lookup", resolve)
    monkeypatch.setattr(tasks, "preview_owner", preview)
    known.previews = previews
    # Accounting links each party ledger to its party; the document check relies on it.
    owners = {known.customer_ledger: known.customer, known.supplier_ledger: known.supplier}
    await apply_bundle(app.state.session_factory, SourceBundle.model_validate({
        "message_id": str(uuid7()), "tenant_id": str(TENANT), "company_id": str(COMPANY),
        "masters": [
            {"entity_type": entity, "source_id": str(source), "source_version": 1,
             "status": "ACTIVE",
             "facts": (
                 {"kind": "GENERAL"}
                 | ({"party_id": str(owners[source])} if source in owners else {})
                 if entity == "account" else {}
             )}
            for entity, source in (
                ("party", known.customer), ("party", known.supplier),
                ("account", known.customer_ledger), ("account", known.supplier_ledger),
                ("account", known.income), ("account", known.expense),
            )
        ],
    }), "accounting")
    return known


def sale(key, *, total="100", **header):
    return {
        "import_key": key, "document_date": TODAY.isoformat(), "customer_code": "CUS-1",
        "currency": "INR", "tax_profile": "UNTAXED_ACCOUNT",
        "lines": [{"line_no": "1", "supply_kind": "SERVICE", "account_code": "INC",
                   "description": "Service", "amount": total}],
    } | header


def note(key, party, original, *lines, **header):
    prefix = "customer" if party == "CUS-1" else "supplier"
    field = "original_invoice_number" if party == "CUS-1" else "original_bill_number"
    return {
        "import_key": key, "document_date": TODAY.isoformat(), f"{prefix}_code": party,
        field: original, "currency": "INR",
        "lines": [
            {"line_no": str(no), "original_line_no": str(original_no), "description": "Return",
             "amount": amount}
            for no, (original_no, amount) in enumerate(lines, 1)
        ],
    } | header


async def test_sales_identified_by_source_reference(client, prefix, app, book):
    from test_foundation import create_type

    kind = await create_type(client, prefix, code="SALE", name="Sales", kind="SALES",
                             policy={"invoice": {"sales_credit_allowed": True}})
    job = await upload(client, prefix, kind, [
        sale("WEB-1", source_reference="WEB-1001", customer_order_number="PO-7"),
        sale("WEB-1-AGAIN", source_reference="web-1001"),
        sale("NO-REF-A", total="70"),
        sale("NO-REF-B", total="70"),
        sale("SUPPLIER", customer_code="SUP-1"),
    ])
    ready = await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["WEB-1"] == ("VALID", set())
    assert result["WEB-1-AGAIN"] == ("INVALID", {"duplicate_reference"})
    assert result["NO-REF-A"] == ("VALID", set())
    assert result["NO-REF-B"] == ("WARNING", {"possible_duplicate"})
    # A supplier's ledger is not a customer ledger.
    assert result["SUPPLIER"] == ("INVALID", {"unknown_master"})
    assert "SALES" in book.previews
    assert (await rows(client, prefix, job["id"]))["WEB-1"]["computed_payable"] == "100.0000"
    done = await commit(client, prefix, ready, on_error="CONTINUE_INDEPENDENT")
    assert done["created_count"] == 3
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            references = {
                (row.purpose, row.reference) for row in await db.scalars(select(m.VoucherReference))
            }
    assert {("EXTERNAL", "WEB-1001"), ("CUSTOMER_ORDER", "PO-7")} <= references
    again = await upload(client, prefix, kind, [sale("WEB-2", source_reference="WEB-1001"),
                                                sale("NO-REF-C", total="70")])
    await validated(client, prefix, again)
    result = await outcome(client, prefix, again)
    assert result["WEB-2"] == ("INVALID", {"duplicate_reference"})
    assert result["NO-REF-C"] == ("WARNING", {"possible_duplicate"})


async def test_notes_return_within_the_original_entitlement(client, prefix, app, book):
    from test_foundation import create_type

    credit = await create_type(client, prefix, code="CRN", name="Credit note",
                               kind="CREDIT_NOTE", policy={"invoice": {}})
    template = await client.get(prefix + "/voucher-import-templates",
                                params={"voucher_type_id": credit["id"], "format": "CSV"},
                                headers=auth())
    header = template.text.splitlines()[1]
    assert "original_invoice_number" in header and "tax_profile" not in header
    job = await upload(client, prefix, credit, [
        note("CN-1", "CUS-1", "INV-1", (1, "250"), return_reference="RET-1"),
        note("CN-2", "CUS-1", "inv-1", (1, "300")),
        note("CN-3", "CUS-1", "INV-1", (1, "100")),
        note("CN-RET", "CUS-1", "INV-1", (1, "1"), return_reference="ret-1"),
        note("CN-TAXED", "CUS-1", "INV-1", (2, "10")),
        note("CN-NOLINE", "CUS-1", "INV-1", (9, "10")),
        note("CN-NONE", "CUS-1", "INV-404", (1, "10")),
    ])
    stage = await outcome(client, prefix, job)
    assert stage["CN-RET"] == ("INVALID", {"duplicate_reference"})
    ready = await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["CN-1"] == ("VALID", set()) and result["CN-2"] == ("VALID", set())
    # 250 + 300 + 100 against 600 remaining on the original line.
    assert result["CN-3"] == ("INVALID", {"exceeds_original"})
    assert result["CN-TAXED"][1] == {"original_not_returnable"}
    assert result["CN-NOLINE"][1] == {"unknown_original_line"}
    assert result["CN-NONE"][1] == {"unknown_original"}
    assert "CREDIT_NOTE" in book.previews
    done = await commit(client, prefix, ready, on_error="CONTINUE_INDEPENDENT")
    assert done["created_count"] == 2
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            details = list(await db.scalars(select(VoucherInvoiceDetail)))
            assert {row.source_invoice_id for row in details} == {book.sale}
            instruction = await db.scalar(select(m.VoucherBillInstruction))
            assert instruction.debt_item_id == book.sale_bill.item_id
    later = await upload(client, prefix, credit, [note("CN-4", "CUS-1", "INV-1", (1, "60"))])
    await validated(client, prefix, later)
    # 550 is already taken by unposted imported drafts: only 50 remains.
    assert (await outcome(client, prefix, later))["CN-4"] == ("INVALID", {"exceeds_original"})

    debit = await create_type(client, prefix, code="DBN", name="Debit note", kind="DEBIT_NOTE",
                              policy={"invoice": {}})
    job = await upload(client, prefix, debit, [
        note("DN-1", "SUP-1", "BILL-1", (1, "400")),
        note("DN-EARLY", "SUP-1", "BILL-1", (1, "1"),
             posting_date=(TODAY - dt.timedelta(days=30)).isoformat()),
    ])
    await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["DN-1"] == ("VALID", set())
    assert result["DN-EARLY"][1] == {"before_original"}
    book.returnable = False
    job = await upload(client, prefix, debit, [note("DN-2", "SUP-1", "BILL-1", (1, "1"))])
    await validated(client, prefix, job)
    assert (await outcome(client, prefix, job))["DN-2"][1] == {"original_not_returnable"}


async def test_note_review_regressions(client, prefix, app, book):
    """Original bill must exist; a note trims its bill adjustment to what drafts leave."""
    from test_foundation import create_type

    credit = await create_type(client, prefix, code="CRN2", name="Credit note",
                               kind="CREDIT_NOTE", policy={"invoice": {}})
    job = await upload(client, prefix, credit, [
        note("CN-A", "CUS-1", "INV-1", (1, "400")),
        note("CN-B", "CUS-1", "inv-1", (1, "150")),
    ])
    ready = await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    # Different casing of one original is one original, not an ambiguous pair.
    assert result == {"CN-A": ("VALID", set()), "CN-B": ("VALID", set())}
    await commit(client, prefix, ready)
    book.sale_bill = OpenBill(book.sale_bill.item_id, "DEBT", "INR", Decimal("500"))
    later = await upload(client, prefix, credit, [note("CN-C", "CUS-1", "INV-1", (1, "40"))])
    ready = await validated(client, prefix, later)
    # 550 of the bill's 500 is already allocated by drafts: the note stays valid, unallocated.
    assert (await outcome(client, prefix, later))["CN-C"] == ("VALID", set())
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            from vouchers.models import imports as im

            row = await db.scalar(select(im.VoucherImportRow).where(
                im.VoucherImportRow.import_key == "CN-C"))
            assert "allocations" not in row.prepared_input["content"]["invoice"] or not (
                row.prepared_input["content"]["invoice"]["allocations"]
            )
    book.with_bills = False
    missing = await upload(client, prefix, credit, [note("CN-D", "CUS-1", "INV-1", (1, "1"))])
    await validated(client, prefix, missing)
    assert (await outcome(client, prefix, missing))["CN-D"] == (
        "INVALID", {"original_bill_missing"}
    )
