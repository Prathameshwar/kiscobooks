"""Payment, Receipt, Contra and Journal imports: kind rules, bank instruments, bills."""

import base64
import csv
import datetime as dt
import io
import secrets
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from pydantic import SecretStr
from sqlalchemy import func, select
from test_foundation import create_type

from vouchers.domain.imports import MARKER, AccountFacts, Master, OpenBill, Resolution
from vouchers.models import core as m
from vouchers.schemas.owners import Owner
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks import imports as tasks
from vouchers.tasks.sources import apply_bundle

TODAY = dt.date.today().isoformat()
IMPORT = frozenset({"vouchers.import.read", "vouchers.import.manage", "vouchers.import.commit"})
LEDGERS = {
    "BANK": ("BANK", None, None),
    "BANK-2": ("BANK", None, None),
    "CASH": ("CASH", None, None),
    "EXP": ("GENERAL", None, None),
    "INC": ("GENERAL", None, None),
    "AUTO": ("GENERAL", None, None),
    "SUP": ("PARTY", uuid7(), "SUPPLIER"),
    "CUS": ("PARTY", uuid7(), "CUSTOMER"),
}


class Ledgers:
    def __init__(self) -> None:
        self.ids = {code: uuid7() for code in LEDGERS}
        self.bills: dict[tuple[uuid.UUID, str], tuple[OpenBill, ...]] = {
            # A posted supplier bill and customer invoice are both DEBT items of the party.
            (self.ids["SUP"], "bill-9"): (OpenBill(uuid7(), "DEBT", "INR", Decimal("600")),),
            (self.ids["CUS"], "inv-5"): (OpenBill(uuid7(), "DEBT", "INR", Decimal("300")),),
        }

    def resolution(self) -> Resolution:
        return Resolution(
            parties={}, gstin_parties={}, party_ids={}, party_ledgers={},
            accounts={code: Master(self.ids[code], 1, "ACTIVE") for code in LEDGERS},
            account_facts={
                self.ids[code]: AccountFacts(
                    kind, party, role, "SYSTEM_ONLY" if code == "AUTO" else "MANUAL_ALLOWED",
                    None,
                )
                for code, (kind, party, role) in LEDGERS.items()
            },
            bills=self.bills,
        )

    async def evidence(self, app) -> None:
        await apply_bundle(app.state.session_factory, SourceBundle.model_validate({
            "message_id": str(uuid7()), "tenant_id": str(TENANT), "company_id": str(COMPANY),
            "masters": [
                {"entity_type": "account", "source_id": str(source), "source_version": 1,
                 "status": "ACTIVE", "facts": {"kind": "GENERAL"}}
                for source in self.ids.values()
            ],
        }), "accounting")


@pytest.fixture
async def ledgers(app, monkeypatch) -> Ledgers:
    known = Ledgers()
    app.state.settings.master_lookup_owner = Owner(
        owner="accounting", origin="http://127.0.0.1", key_id="money-import",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )

    async def resolve(owner, tenant, company, **codes):
        return known.resolution()

    monkeypatch.setattr(tasks, "default_lookup", resolve)
    await known.evidence(app)
    return known


def auth(**changes):
    return headers(permissions=changes.pop("permissions", None) or PERMISSIONS | IMPORT, **changes)


def line(no, account, side, amount, **extra):
    return {"line_no": str(no), "account_code": account, "side": side, "amount": amount} | extra


def voucher(key, *lines, **header):
    return {"import_key": key, "document_date": TODAY, "currency": "INR",
            "lines": list(lines)} | header


async def upload(client, prefix, kind, vouchers):
    template = await client.get(
        prefix + "/voucher-import-templates",
        params={"voucher_type_id": kind["id"], "format": "CSV"}, headers=auth(),
    )
    assert template.status_code == 200, template.text
    header = list(csv.reader(io.StringIO(template.text)))[1]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([MARKER, "1"])
    writer.writerow(header)
    for item in vouchers:
        for row in item["lines"]:
            cells = {k: v for k, v in item.items() if k != "lines"} | row
            assert set(cells) <= set(header), set(cells) - set(header)
            writer.writerow([cells.get(name, "") for name in header])
    staged = await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": kind["id"], "format": "CSV",
              "content_base64": base64.b64encode(output.getvalue().encode()).decode()},
        headers=auth(),
    )
    assert staged.status_code == 202, staged.text
    return staged.json()


async def validated(client, prefix, job):
    result = (await client.post(
        prefix + f"/voucher-imports/{job['id']}/validate",
        json={"expected_version": job["row_version"]}, headers=auth(),
    ))
    assert result.status_code == 200, result.text
    body = result.json()
    while body["state"] == "VALIDATING":
        body = (await client.post(prefix + f"/voucher-imports/{job['id']}/run",
                                  headers=auth())).json()
    return body


async def outcome(client, prefix, job):
    rows = (await client.get(prefix + f"/voucher-imports/{job['id']}/vouchers",
                             headers=auth())).json()["items"]
    result = {}
    for row in rows:
        detail = (await client.get(
            prefix + f"/voucher-imports/{job['id']}/vouchers/{row['import_key']}", headers=auth()
        )).json()
        result[row["import_key"]] = (row["state"], {e["code"] for e in detail["errors"]})
    return result


async def commit(client, prefix, ready, **body):
    done = await client.post(
        prefix + f"/voucher-imports/{ready['id']}/commit",
        json={"expected_version": ready["row_version"],
              "selection_digest": ready["selection_digest"]} | body,
        headers=auth(),
    )
    assert done.status_code == 200, done.text
    return done.json()


async def vouchers_of(app):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            return int(await db.scalar(select(func.count(m.Voucher.id))) or 0)


async def test_payment_rules_instruments_and_bill_allocation(client, prefix, app, ledgers):
    kind = await create_type(client, prefix, code="BANKPAY", name="Bank payment", kind="PAYMENT")
    job = await upload(client, prefix, kind, [
        voucher("OK", line(1, "EXP", "DEBIT", "500"),
                line(2, "BANK", "CREDIT", "500", tender_mode="NEFT", tender_reference="UTR-1")),
        voucher("SAME-UTR", line(1, "EXP", "DEBIT", "50"),
                line(2, "BANK", "CREDIT", "50", tender_mode="IMPS", tender_reference="utr-1")),
        voucher("UNBALANCED", line(1, "EXP", "DEBIT", "10"),
                line(2, "BANK", "CREDIT", "9", tender_mode="UPI", tender_reference="U-2")),
        voucher("WRONG-SIDE", line(1, "EXP", "CREDIT", "10"),
                line(2, "BANK", "DEBIT", "10", tender_mode="UPI", tender_reference="U-3")),
        voucher("CASH-ON-BANK", line(1, "EXP", "DEBIT", "10"),
                line(2, "BANK", "CREDIT", "10", tender_mode="CASH")),
        voucher("NO-TENDER", line(1, "EXP", "DEBIT", "10"), line(2, "BANK", "CREDIT", "10")),
        voucher("SYSTEM-LEDGER", line(1, "AUTO", "DEBIT", "10"),
                line(2, "CASH", "CREDIT", "10", tender_mode="CASH")),
        voucher("BILL", line(1, "SUP", "DEBIT", "500", against_bill="BILL-9"),
                line(2, "BANK", "CREDIT", "500", tender_mode="CHEQUE",
                     tender_reference="CHQ-100", instrument_date=TODAY)),
        voucher("BILL-AGAIN", line(1, "SUP", "DEBIT", "200", against_bill="bill-9"),
                line(2, "BANK", "CREDIT", "200", tender_mode="RTGS", tender_reference="R-9")),
        voucher("NO-BILL", line(1, "SUP", "DEBIT", "20", against_bill="NOPE"),
                line(2, "BANK", "CREDIT", "20", tender_mode="RTGS", tender_reference="R-10")),
        voucher("LEAF-AGAIN", line(1, "EXP", "DEBIT", "70"),
                line(2, "BANK", "CREDIT", "70", tender_mode="CHEQUE",
                     tender_reference="CHQ-100", instrument_date=TODAY)),
    ])
    states = {key: s for key, (s, _) in (await outcome(client, prefix, job)).items()}
    assert states["SAME-UTR"] == states["UNBALANCED"] == states["LEAF-AGAIN"] == "INVALID"
    ready = await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["OK"] == ("VALID", set())
    assert result["SAME-UTR"] == ("INVALID", {"duplicate_instrument"})
    assert result["UNBALANCED"] == ("INVALID", {"unbalanced"})
    assert result["WRONG-SIDE"][1] == {"wrong_side"}
    assert result["CASH-ON-BANK"][1] == {"wrong_tender"}
    assert result["NO-TENDER"][1] == {"required"}
    assert result["SYSTEM-LEDGER"][1] == {"manual_posting_blocked"}
    assert result["BILL"] == ("VALID", set())
    # 500 + 200 against a bill with 600 outstanding: the second crosses the limit.
    assert result["BILL-AGAIN"] == ("INVALID", {"exceeds_outstanding"})
    assert result["NO-BILL"][1] == {"unknown_bill"}
    assert result["LEAF-AGAIN"] == ("INVALID", {"duplicate_instrument"})
    assert ready["valid_count"] == 2
    done = await commit(client, prefix, ready)
    assert done["state"] == "SUCCEEDED" and done["created_count"] == 2
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            instruction = await db.scalar(select(m.VoucherBillInstruction))
            assert instruction.amount == Decimal("500")
            bill = ledgers.bills[(ledgers.ids["SUP"], "bill-9")][0]
            assert instruction.debt_item_id == bill.item_id
    again = await upload(client, prefix, kind, [
        voucher("REPLAY", line(1, "EXP", "DEBIT", "500"),
                line(2, "BANK", "CREDIT", "500", tender_mode="NEFT", tender_reference="UTR-1")),
        voucher("REST", line(1, "SUP", "DEBIT", "150", against_bill="BILL-9"),
                line(2, "BANK", "CREDIT", "150", tender_mode="NEFT", tender_reference="UTR-2")),
    ])
    await validated(client, prefix, again)
    result = await outcome(client, prefix, again)
    assert result["REPLAY"] == ("INVALID", {"duplicate_instrument"})
    # 600 outstanding at the owner, 500 already taken by the unposted imported draft.
    assert result["REST"] == ("INVALID", {"exceeds_outstanding"})
    assert await vouchers_of(app) == 2


async def test_receipt_cheques_contra_and_journal_rules(client, prefix, app, ledgers):
    receipt = await create_type(client, prefix, code="RCPT", name="Receipt", kind="RECEIPT")
    job = await upload(client, prefix, receipt, [
        voucher("CHQ-A", line(1, "BANK", "DEBIT", "100", tender_mode="CHEQUE",
                              tender_reference="000123", instrument_date=TODAY),
                line(2, "CUS", "CREDIT", "100", against_bill="INV-5")),
        # Another drawer's cheque with the same number but a different amount is a new one.
        voucher("CHQ-B", line(1, "BANK", "DEBIT", "150", tender_mode="CHEQUE",
                              tender_reference="000123", instrument_date=TODAY),
                line(2, "INC", "CREDIT", "150")),
        voucher("CASH-1", line(1, "CASH", "DEBIT", "40", tender_mode="CASH"),
                line(2, "INC", "CREDIT", "40")),
        voucher("CASH-2", line(1, "CASH", "DEBIT", "40", tender_mode="CASH"),
                line(2, "INC", "CREDIT", "40")),
        voucher("WRONG-BILL", line(1, "BANK", "DEBIT", "10", tender_mode="UPI",
                                   tender_reference="U-77"),
                line(2, "SUP", "CREDIT", "10", against_bill="BILL-9")),
        voucher("ADVANCE-ROLE", line(1, "BANK", "DEBIT", "10", tender_mode="UPI",
                                     tender_reference="U-78"),
                line(2, "SUP", "CREDIT", "10", tracking="ADVANCE"), purpose="ADVANCE"),
    ])
    await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["CHQ-A"] == ("VALID", set()) and result["CHQ-B"] == ("VALID", set())
    assert result["CASH-1"] == ("VALID", set())
    assert result["CASH-2"] == ("WARNING", {"possible_duplicate"})
    # A receipt's supplier credit line is itself a DEBT item; it cannot settle a supplier bill.
    assert result["WRONG-BILL"][1] == {"wrong_bill_direction"}
    assert result["ADVANCE-ROLE"][1] == {"advance_role"}

    contra = await create_type(client, prefix, code="CONTRA", name="Contra", kind="CONTRA")
    job = await upload(client, prefix, contra, [
        voucher("MOVE", line(1, "CASH", "DEBIT", "90", tender_mode="CASH"),
                line(2, "BANK", "CREDIT", "90", tender_mode="CHEQUE", tender_reference="CHQ-9",
                     instrument_date=TODAY)),
        voucher("NOT-MONEY", line(1, "EXP", "DEBIT", "90"),
                line(2, "BANK", "CREDIT", "90", tender_mode="NEFT", tender_reference="N-1")),
        voucher("SAME-LEDGER", line(1, "BANK", "DEBIT", "5", tender_mode="NEFT",
                                    tender_reference="N-2"),
                line(2, "BANK", "CREDIT", "5", tender_mode="NEFT", tender_reference="N-3")),
    ])
    await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["MOVE"] == ("VALID", set())
    assert "contra_ledgers" in result["NOT-MONEY"][1]
    assert result["SAME-LEDGER"][1] == {"contra_ledgers"}

    journal = await create_type(client, prefix, code="JRNL", name="Journal", kind="JOURNAL")
    header = await client.get(prefix + "/voucher-import-templates",
                              params={"voucher_type_id": journal["id"], "format": "CSV"},
                              headers=auth())
    assert "tender_mode" not in header.text and "against_bill" not in header.text
    job = await upload(client, prefix, journal, [
        voucher("J1", line(1, "EXP", "DEBIT", "12.5"), line(2, "INC", "CREDIT", "12.5")),
        voucher("J2", line(1, "INC", "CREDIT", "12.5"), line(2, "EXP", "DEBIT", "12.5")),
        voucher("J-BANK", line(1, "EXP", "DEBIT", "1"), line(2, "BANK", "CREDIT", "1")),
        voucher("J-PARTY", line(1, "SUP", "DEBIT", "1", tracking="NONE"),
                line(2, "EXP", "CREDIT", "1")),
    ])
    ready = await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["J1"] == ("VALID", set())
    # Same date, ledgers, sides and amounts in another order: possibly the same journal.
    assert result["J2"] == ("WARNING", {"possible_duplicate"})
    assert result["J-BANK"][1] == {"journal_cash_bank"}
    assert result["J-PARTY"][1] == {"tracking_required"}
    done = await commit(client, prefix, ready, on_error="CONTINUE_INDEPENDENT")
    assert done["state"] == "SUCCEEDED" and done["created_count"] == 2
    repeat = await upload(client, prefix, journal, [
        voucher("J3", line(1, "EXP", "DEBIT", "12.5"), line(2, "INC", "CREDIT", "12.5")),
    ])
    await validated(client, prefix, repeat)
    assert (await outcome(client, prefix, repeat))["J3"] == ("WARNING", {"possible_duplicate"})


async def test_money_duplicate_rule_and_validation_owner(client, prefix, app, ledgers):
    kind = await create_type(client, prefix, code="PAY2", name="Payment", kind="PAYMENT")
    refused = await client.post(
        prefix + "/voucher-imports",
        json={"voucher_type_id": kind["id"], "format": "JSON", "duplicate_rule": "DATE_NUMBER",
              "document": {"schema_version": 1, "vouchers": []}},
        headers=auth(),
    )
    assert refused.status_code == 422
    # Money vouchers need no invoice calculation owner.
    app.state.settings.execution_owner = None
    job = await upload(client, prefix, kind, [
        voucher("P", line(1, "EXP", "DEBIT", "5"),
                line(2, "CASH", "CREDIT", "5", tender_mode="CASH")),
    ])
    ready = await validated(client, prefix, job)
    assert ready["state"] == "READY" and ready["valid_count"] == 1
    rows = (await client.get(prefix + f"/voucher-imports/{job['id']}/vouchers",
                             headers=auth())).json()["items"]
    assert rows[0]["computed_payable"] == "5.0000"


async def test_money_review_regressions(client, prefix, app, ledgers):
    """Settled bills, advances without a party, reversals and stale balance checks."""
    kind = await create_type(client, prefix, code="PAYR", name="Payment", kind="PAYMENT")
    ledgers.bills[(ledgers.ids["SUP"], "paid")] = (OpenBill(uuid7(), "DEBT", "INR", Decimal(0)),)
    job = await upload(client, prefix, kind, [
        voucher("SETTLED", line(1, "SUP", "DEBIT", "5", against_bill="PAID"),
                line(2, "CASH", "CREDIT", "5", tender_mode="CASH")),
        voucher("ADV-NO-PARTY", line(1, "EXP", "DEBIT", "5"),
                line(2, "CASH", "CREDIT", "5", tender_mode="CASH"), purpose="ADVANCE"),
        voucher("FIRST", line(1, "SUP", "DEBIT", "600", against_bill="BILL-9"),
                line(2, "BANK", "CREDIT", "600", tender_mode="NEFT", tender_reference="U-1")),
    ])
    ready = await validated(client, prefix, job)
    result = await outcome(client, prefix, job)
    assert result["SETTLED"] == ("INVALID", {"bill_settled"})
    assert result["ADV-NO-PARTY"] == ("INVALID", {"party_required"})
    assert result["FIRST"] == ("VALID", set())
    # A balance checked long ago is not trusted at commit: validate again.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            from vouchers.models import imports as im

            row = await db.scalar(select(im.VoucherImportRow).where(
                im.VoucherImportRow.import_key == "FIRST"))
            prepared = dict(row.prepared_input)
            prepared["probes"] = [
                item | ({"checked_at": "2000-01-01T00:00:00+00:00"}
                        if item["probe"] == "allocation" else {})
                for item in prepared["probes"]
            ]
            row.prepared_input = prepared
    done = await commit(client, prefix, ready)
    assert done["state"] == "FAILED"
    assert (await outcome(client, prefix, job))["FIRST"] == ("FAILED", {"revalidate"})
    again = await upload(client, prefix, kind, [
        voucher("SECOND", line(1, "SUP", "DEBIT", "600", against_bill="BILL-9"),
                line(2, "BANK", "CREDIT", "600", tender_mode="NEFT", tender_reference="U-1")),
    ])
    ready = await validated(client, prefix, again)
    assert (await commit(client, prefix, ready))["created_count"] == 1
    # Once that draft is reversed it neither holds the bill nor its transfer reference.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            voucher_row = await db.scalar(select(m.Voucher))
            voucher_row.status = "REVERSED"
    third = await upload(client, prefix, kind, [
        voucher("THIRD", line(1, "SUP", "DEBIT", "600", against_bill="BILL-9"),
                line(2, "BANK", "CREDIT", "600", tender_mode="NEFT", tender_reference="U-1")),
    ])
    await validated(client, prefix, third)
    assert (await outcome(client, prefix, third))["THIRD"] == ("VALID", set())
    # Money amounts are masked with a read-deny on the financial section.
    deny = [{"entity_type": "vouchers.voucher", "field_key": "financial", "access": "read",
             "effect": "deny", "scope_type": "company", "scope_id": str(COMPANY)}]
    rows = (await client.get(prefix + f"/voucher-imports/{third['id']}/vouchers",
                             headers=auth(policies=deny))).json()["items"]
    assert rows[0]["computed_payable"] is None
