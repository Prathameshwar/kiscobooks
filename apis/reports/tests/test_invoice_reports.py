"""Distinct date/grain controls, signed frozen exports and forbidden disclosure."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from financial_fixture import financial_manifest
from fixtures import source
from invoice_fixture import invoice_dataset
from pydantic import ValidationError
from reporting_contract.contract import FactPage
from test_foundation import generation

from reports.domain.reconcile import immutable_claim, reconcile
from reports.domain.statements import calculate
from reports.models import core as m
from reports.schemas.requests import RunRequest
from reports.tasks import ingest, runs
from reports.tasks.common import company_lock, get


def test_invoice_dates_settlement_as_of_and_document_grains():
    facts, ids = invoice_dataset()
    reconcile(facts, financial_manifest(facts).control)
    query = RunRequest(
        code="SALES_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert len(rows) == 1 and rows[0]["payable"] == "200"
    assert evidence["invoice_coverage"] == "NATIVE_VOUCHER_INVOICES"
    assert (
        calculate(facts, query.model_copy(update={"date_basis": "DOCUMENT"}), dt.date(2026, 4, 1))[
            0
        ]
        == []
    )
    settlement = query.model_copy(update={"code": "INVOICE_SETTLEMENT_REGISTER"})
    settled = calculate(facts, settlement, dt.date(2026, 4, 1))[0]
    assert len(settled) == 1 and settled[0]["settlement_amount"] == "50"
    assert "payable" not in settled[0] and settled[0]["active"]
    later = settlement.model_copy(
        update={"date_from": dt.date(2027, 4, 1), "date_to": dt.date(2027, 4, 30)}
    )
    assert len(calculate(facts, later, dt.date(2026, 4, 1))[0]) == 2
    for row in facts:
        if row.entity.startswith("invoice_"):
            assert immutable_claim(row, {})
    draft = [
        source(row.entity, row.source_id, row.data | {"status": "PREPARED"})
        if row.entity == "voucher_money_intent"
        else row
        for row in facts
    ]
    assert calculate(draft, query, dt.date(2026, 4, 1))[0] == []


@pytest.mark.parametrize(
    "entity,changes,pattern",
    [
        ("invoice_record", {"payable": "201"}, "party bill"),
        ("invoice_record", {"kind": "PURCHASE"}, "kind"),
        ("invoice_record", {"source_invoice_id": str(uuid.uuid4())}, "ordinary invoice"),
        ("invoice_supply_fact", {"entered": "199"}, "allocation"),
        ("invoice_posting_line", {"journal_line_id": str(uuid.uuid4())}, "linkage"),
        ("invoice_posting_line", {"tax_purpose": "OUTPUT_IGST"}, "lineage"),
        ("invoice_supply_fact", {"invoice_id": str(uuid.uuid4())}, "reference"),
    ],
)
def test_inconsistent_invoice_sources_block_reports(entity, changes, pattern):
    facts, _ = invoice_dataset()
    edited = False
    result = []
    for row in facts:
        if row.entity == entity and not edited:
            row = source(entity, row.source_id, row.data | changes)
            edited = True
        result.append(row)
    with pytest.raises(ConflictError, match=pattern):
        reconcile(result, financial_manifest(result).control)


def test_invoice_without_its_native_open_bill_cannot_reconcile():
    facts, ids = invoice_dataset()
    bill_id = next(
        str(row.source_id)
        for row in facts
        if row.entity == "open_item" and row.data["reference"] == "INV-1"
    )
    missing_bill = [
        row
        for row in facts
        if not (
            (row.entity == "open_item" and str(row.source_id) == bill_id)
            or (row.entity == "allocation" and row.data["debt_item_id"] == bill_id)
        )
    ]
    with pytest.raises(ConflictError, match="matching native open item"):
        reconcile(missing_bill, financial_manifest(missing_bill).control)
    stale_due_date = [
        source(row.entity, row.source_id, row.data | {"due_date": "2026-05-01"})
        if row.entity == "open_item" and str(row.source_id) == bill_id
        else row
        for row in facts
    ]
    with pytest.raises(ConflictError, match="matching native open item"):
        reconcile(stale_due_date, financial_manifest(stale_due_date).control)
    stale_link = [
        source(row.entity, row.source_id, row.data | {"due_date": "2026-05-01"})
        if row.entity == "invoice_posting_line"
        and row.data["invoice_id"] == ids["invoice"]
        and row.data["tracking"] == "NEW_REF"
        else row
        for row in facts
    ]
    with pytest.raises(ConflictError, match="party bill differs"):
        reconcile(stale_link, financial_manifest(stale_link).control)


@pytest.mark.parametrize(
    "changes",
    [
        {"code": "TRIAL_BALANCE", "invoice_id": str(uuid.uuid4())},
        {"code": "SALES_REGISTER", "date_basis": "TAX_POINT"},
        {"code": "INVOICE_CREDIT_REGISTER", "date_basis": "DOCUMENT"},
        {"code": "SALES_REGISTER", "company_registration_id": str(uuid.uuid4())},
    ],
)
def test_report_filter_combinations_cannot_be_silently_ignored(changes):
    with pytest.raises(ValidationError):
        RunRequest.model_validate(
            {"generation_id": uuid.uuid4(), "date_from": "2026-04-01", "date_to": "2026-04-30"}
            | changes
        )


def test_balanced_journal_cannot_disguise_invoice_party_total_difference():
    facts, _ = invoice_dataset()
    journal_id = next(
        row.source_id
        for row in facts
        if row.entity == "journal" and row.data["number"] == "invoice"
    )
    changed = []
    for row in facts:
        if row.entity == "journal" and row.source_id == journal_id:
            row = source(
                row.entity, row.source_id, row.data | {"total_debit": "201", "total_credit": "201"}
            )
        if row.entity == "journal_line" and row.data["journal_id"] == str(journal_id):
            row = source(
                row.entity, row.source_id, row.data | {"amount": "201", "base_amount": "201"}
            )
        changed.append(row)
    with pytest.raises(ConflictError, match="party bill"):
        reconcile(changed, financial_manifest(changed).control)


def component_dataset():
    facts, ids = invoice_dataset()
    component_id, commercial_id, tax_base_id = [uuid.uuid4() for _ in range(3)]
    facts = [
        source(row.entity, row.source_id, row.data | {"entered": "180"})
        if row.entity == "invoice_supply_fact"
        else row
        for row in facts
    ]
    facts.extend(
        [
            source(
                "invoice_component_fact",
                component_id,
                {
                    "invoice_id": ids["invoice"],
                    "component_key": str(uuid.uuid4()),
                    "sequence": 1,
                    "purpose": "CHARGE",
                    "scope": "INVOICE",
                    "effect": "ADD",
                    "input_kind": "AMOUNT",
                    "basis_amount": "180",
                    "basis_quantity": None,
                    "input_amount": "20",
                    "amount": "20",
                    "account_id": ids["income"],
                    "commercial_treatment": "COUNTERPARTY",
                    "tax_treatment": "ASSESSABLE",
                    "return_treatment": "PROPORTIONAL",
                    "source_evidence": "MANUAL",
                },
            ),
            *[
                source(
                    "invoice_allocation_fact",
                    identity,
                    {
                        "invoice_id": ids["invoice"],
                        "component_id": str(component_id),
                        "supply_id": ids["supply"],
                        "purpose": purpose,
                        "amount": "20",
                    },
                )
                for identity, purpose in (
                    (commercial_id, "COMMERCIAL"),
                    (tax_base_id, "TAX_BASE"),
                )
            ],
        ]
    )
    return facts, ids, commercial_id


def test_invoice_component_register_and_gl_bridge_preserve_distinct_grains():
    facts, ids, commercial_id = component_dataset()
    reconcile(facts, financial_manifest(facts).control)
    request = RunRequest(
        code="INVOICE_COMPONENT_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    rows = calculate(facts, request, dt.date(2026, 4, 1))[0]
    assert len(rows) == 3
    assert {row["row_kind"] for row in rows} == {"COMPONENT", "ALLOCATION"}
    assert [row["component_amount"] for row in rows if row["row_kind"] == "COMPONENT"] == ["20"]
    assert all("payable" not in row for row in rows)

    bridge = calculate(
        facts, request.model_copy(update={"code": "INVOICE_GL_BRIDGE"}), dt.date(2026, 4, 1)
    )[0]
    assert len(bridge) == 2
    assert sum(Decimal(row["signed_debit"]) for row in bridge) == 0
    assert {row["amount"] for row in bridge} == {"200"}

    damaged = [
        source(row.entity, row.source_id, row.data | {"amount": "19"})
        if row.entity == "invoice_allocation_fact" and row.source_id == commercial_id
        else row
        for row in facts
    ]
    with pytest.raises(ConflictError, match="allocation"):
        reconcile(damaged, financial_manifest(damaged).control)


def tax_dataset():
    facts, ids = invoice_dataset()
    journal = next(
        row for row in facts if row.entity == "journal" and row.data["number"] == "invoice"
    )
    party_line = next(
        row
        for row in facts
        if row.entity == "journal_line"
        and row.data["journal_id"] == str(journal.source_id)
        and row.data["account_id"] == ids["party"]
    )
    income_line = next(
        row
        for row in facts
        if row.entity == "journal_line"
        and row.data["journal_id"] == str(journal.source_id)
        and row.data["account_id"] == ids["income"]
    )
    income_account = next(
        row for row in facts if row.entity == "account" and str(row.source_id) == ids["income"]
    )
    income_group = next(
        row
        for row in facts
        if row.entity == "account_group" and str(row.source_id) == income_account.data["group_id"]
    )
    income_head = next(
        row
        for row in facts
        if row.entity == "account_head" and str(row.source_id) == income_group.data["head_id"]
    )
    tax_head, tax_group, tax_account, tax_line, tax_component, registration = [
        uuid.uuid4() for _ in range(6)
    ]
    changed = []
    for row in facts:
        update = None
        if row.entity == "journal" and row.source_id == journal.source_id:
            update = {"total_debit": "220", "total_credit": "220"}
        elif row.entity == "journal_line" and row.source_id == party_line.source_id:
            update = {"amount": "220", "base_amount": "220"}
        elif row.entity == "open_item" and row.data["journal_line_id"] == str(party_line.source_id):
            update = {"amount": "220", "base_amount": "220"}
        elif row.entity == "invoice_record":
            update = {"tax_total": "20", "charged_tax_total": "20", "payable": "220"}
        elif row.entity == "invoice_supply_fact":
            update = {
                "tax_profile": "GST_OUTPUT",
                "tax_point_date": "2026-04-01",
                "tax_point_basis": "SUPPLY",
                "company_registration_id": str(registration),
                "treatment": "TAXABLE",
            }
        changed.append(source(row.entity, row.source_id, row.data | update) if update else row)
    changed.extend(
        [
            source(
                "account_head",
                tax_head,
                income_head.data | {"code": "TAX", "name": "Tax", "nature": "LIABILITY"},
            ),
            source(
                "account_group",
                tax_group,
                income_group.data | {"code": "TAX", "name": "Tax", "head_id": str(tax_head)},
            ),
            source(
                "account",
                tax_account,
                income_account.data
                | {"code": "OUTPUT_IGST", "name": "Output IGST", "group_id": str(tax_group)},
            ),
            source(
                "journal_line",
                tax_line,
                income_line.data
                | {
                    "sequence": 3,
                    "account_id": str(tax_account),
                    "amount": "20",
                    "base_amount": "20",
                },
            ),
            source(
                "invoice_tax_component",
                tax_component,
                {
                    "invoice_id": ids["invoice"],
                    "supply_id": ids["supply"],
                    "component_key": "IGST",
                    "code": "IGST",
                    "basis": "200",
                    "amount": "20",
                    "percentage": "10",
                    "supplier_charged": True,
                    "rounding_mode": "HALF_UP",
                    "source_version": 1,
                },
            ),
            source(
                "invoice_posting_line",
                uuid.uuid4(),
                {
                    "invoice_id": ids["invoice"],
                    "journal_line_id": str(tax_line),
                    "tax_component_id": str(tax_component),
                    "tax_purpose": "OUTPUT_IGST",
                    "line_key": str(uuid.uuid4()),
                    "sequence": 3,
                    "source_version": 1,
                    "purpose": "TAX",
                    "tracking": "NONE",
                    "bill_reference": None,
                    "due_date": None,
                },
            ),
        ]
    )
    return changed, ids, registration


def test_tax_register_and_tax_gl_bridge_follow_tax_point_and_posting_dates():
    changed, ids, registration = tax_dataset()
    reconcile(changed, financial_manifest(changed).control)
    request = RunRequest(
        code="INVOICE_TAX_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-01",
        date_basis="TAX_POINT",
        company_registration_id=registration,
    )
    rows = calculate(changed, request, dt.date(2026, 4, 1))[0]
    assert len(rows) == 1
    assert rows[0]["tax_amount"] == "20" and rows[0]["tax_code"] == "IGST"
    assert rows[0]["tax_point_date"] == "2026-04-01"
    assert (
        calculate(
            changed, request.model_copy(update={"date_basis": "POSTING"}), dt.date(2026, 4, 1)
        )[0]
        == []
    )
    bridge = calculate(
        changed, request.model_copy(update={"code": "TAX_GL_BRIDGE"}), dt.date(2026, 4, 1)
    )[0]
    assert len(bridge) == 1 and bridge[0]["tax_purpose"] == "OUTPUT_IGST"
    assert bridge[0]["amount"] == "20" and bridge[0]["posting_date"] == "2026-04-02"


def _append_credit_note(facts, ids, amount: str, number: str):
    original = next(
        row
        for row in facts
        if row.entity == "invoice_record" and str(row.source_id) == ids["invoice"]
    )
    original_supply = next(
        row
        for row in facts
        if row.entity == "invoice_supply_fact" and row.data["invoice_id"] == ids["invoice"]
    )
    original_intent = next(
        row
        for row in facts
        if row.entity == "voucher_money_intent" and str(row.source_id) == original.data["intent_id"]
    )
    original_journal = next(
        row
        for row in facts
        if row.entity == "journal" and str(row.source_id) == original_intent.data["journal_id"]
    )
    note_id, intent_id, journal_id, supply_id = [uuid.uuid4() for _ in range(4)]
    note_date = "2026-04-05"
    facts.extend(
        [
            source(
                "journal",
                journal_id,
                original_journal.data
                | {
                    "kind": "CREDIT_NOTE",
                    "number": number,
                    "source_id": str(journal_id),
                    "document_date": note_date,
                    "posting_date": note_date,
                    "total_debit": amount,
                    "total_credit": amount,
                },
            ),
            source(
                "voucher_money_intent",
                intent_id,
                original_intent.data
                | {
                    "execution_id": str(uuid.uuid4()),
                    "voucher_id": str(uuid.uuid4()),
                    "journal_id": str(journal_id),
                    "kind": "CREDIT_NOTE",
                    "posting_date": note_date,
                },
            ),
            source(
                "invoice_record",
                note_id,
                original.data
                | {
                    "intent_id": str(intent_id),
                    "revision_id": str(uuid.uuid4()),
                    "kind": "CREDIT_NOTE",
                    "source_invoice_id": ids["invoice"],
                    "document_date": note_date,
                    "posting_date": note_date,
                    "bill_reference": number,
                    "due_date": note_date,
                    "commercial_total": amount,
                    "payable": amount,
                },
            ),
            source(
                "invoice_supply_fact",
                supply_id,
                original_supply.data
                | {
                    "invoice_id": str(note_id),
                    "entered": amount,
                    "commercial": amount,
                    "taxable": amount,
                    "payable": amount,
                },
            ),
        ]
    )
    original_links = [
        row
        for row in facts
        if row.entity == "invoice_posting_line" and row.data["invoice_id"] == ids["invoice"]
    ]
    source_bill = next(
        row for row in facts if row.entity == "open_item" and row.data["reference"] == "INV-1"
    )
    party_line_id = None
    for link in original_links:
        source_line = next(
            row
            for row in facts
            if row.entity == "journal_line" and str(row.source_id) == link.data["journal_line_id"]
        )
        party = source_line.data["account_id"] == ids["party"]
        line_id = uuid.uuid4()
        if party:
            party_line_id = line_id
        facts.append(
            source(
                "journal_line",
                line_id,
                source_line.data
                | {
                    "journal_id": str(journal_id),
                    "side": "CREDIT" if party else "DEBIT",
                    "amount": amount,
                    "base_amount": amount,
                },
            )
        )
        facts.append(
            source(
                "invoice_posting_line",
                uuid.uuid4(),
                link.data
                | {
                    "invoice_id": str(note_id),
                    "journal_line_id": str(line_id),
                    "line_key": str(uuid.uuid4()),
                    "bill_reference": number if party else None,
                    "due_date": note_date if party else None,
                },
            )
        )
    assert party_line_id is not None
    facts.append(
        source(
            "open_item",
            uuid.uuid4(),
            source_bill.data
            | {
                "journal_line_id": str(party_line_id),
                "direction": "CREDIT",
                "reference": number,
                "amount": amount,
                "base_amount": amount,
                "document_date": note_date,
                "posting_date": note_date,
                "due_date": note_date,
            },
        )
    )
    return str(note_id)


def test_credit_note_register_reduces_original_and_rejects_excess_claims():
    facts, ids = invoice_dataset()
    note_id = _append_credit_note(facts, ids, "50", "CN-1")
    reconcile(facts, financial_manifest(facts).control)
    query = RunRequest(
        code="SALES_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    rows = calculate(facts, query, dt.date(2026, 4, 1))[0]
    assert len(rows) == 2
    assert {row["direction"] for row in rows} == {"ORIGINAL", "REDUCTION"}
    note = next(row for row in rows if row["direction"] == "REDUCTION")
    assert note["invoice_id"] == note_id and note["source_invoice_id"] == ids["invoice"]
    assert Decimal(note["payable"]) == 50

    _append_credit_note(facts, ids, "151", "CN-2")
    with pytest.raises(ConflictError, match="exceed"):
        reconcile(facts, financial_manifest(facts).control)


def purchase_dataset():
    facts, ids = invoice_dataset()
    invoice_journal = next(
        row for row in facts if row.entity == "journal" and row.data["number"] == "invoice"
    )
    invoice_lines = {
        str(row.source_id)
        for row in facts
        if row.entity == "journal_line" and row.data["journal_id"] == str(invoice_journal.source_id)
    }
    facts = [
        row
        for row in facts
        if (
            row.entity not in {"journal", "journal_line", "open_item", "allocation"}
            or (row.entity == "journal" and row.source_id == invoice_journal.source_id)
            or (row.entity == "journal_line" and str(row.source_id) in invoice_lines)
            or (row.entity == "open_item" and row.data["journal_line_id"] in invoice_lines)
        )
    ]
    heads = {row.data["code"]: row for row in facts if row.entity == "account_head"}
    tax_id, group_id, head_id, tax_line_id, tax_component_id = [uuid.uuid4() for _ in range(5)]
    purchase = []
    for row in facts:
        update = None
        if row.entity == "journal" and row.source_id == invoice_journal.source_id:
            update = {"kind": "PURCHASE", "total_debit": "220", "total_credit": "220"}
        elif row.entity == "account" and str(row.source_id) == ids["party"]:
            update = {"party_role": "SUPPLIER"}
        elif row.entity == "account_head" and row.source_id == heads["PARTY"].source_id:
            update = {"nature": "LIABILITY"}
        elif row.entity == "account_head" and row.source_id == heads["INCOME"].source_id:
            update = {"nature": "EXPENSE"}
        elif row.entity == "journal_line" and row.data["journal_id"] == str(
            invoice_journal.source_id
        ):
            if row.data["account_id"] == ids["party"]:
                update = {
                    "side": "CREDIT",
                    "amount": "220",
                    "base_amount": "220",
                    "role": "SUPPLIER",
                }
            else:
                update = {"side": "DEBIT"}
        elif row.entity == "open_item":
            update = {
                "direction": "DEBT",
                "role": "SUPPLIER",
                "amount": "220",
                "base_amount": "220",
            }
        elif row.entity == "invoice_record":
            update = {
                "kind": "PURCHASE",
                "tax_total": "20",
                "charged_tax_total": "20",
                "payable": "220",
            }
        elif row.entity == "voucher_money_intent":
            update = {"kind": "PURCHASE"}
        elif row.entity == "invoice_supply_fact":
            update = {
                "tax_profile": "GST_INPUT",
                "tax_point_date": "2026-04-02",
                "tax_point_basis": "SUPPLIER_INVOICE",
                "treatment": "TAXABLE",
                "credit_state": "PENDING_EVIDENCE",
            }
        purchase.append(source(row.entity, row.source_id, row.data | update) if update else row)
    tax_account_template = next(
        row for row in purchase if row.entity == "account" and row.data["code"] == "CASH"
    )
    tax_group_template = next(
        row for row in purchase if row.entity == "account_group" and row.data["code"] == "CASH"
    )
    expense_line = next(
        row
        for row in purchase
        if row.entity == "journal_line"
        and row.data["journal_id"] == str(invoice_journal.source_id)
        and row.data["account_id"] == ids["income"]
    )
    purchase.extend(
        [
            source(
                "account_head",
                head_id,
                heads["CASH"].data | {"code": "TAX_ASSET", "name": "Input tax"},
            ),
            source(
                "account_group",
                group_id,
                tax_group_template.data
                | {"code": "TAX_ASSET", "name": "Input tax", "head_id": str(head_id)},
            ),
            source(
                "account",
                tax_id,
                tax_account_template.data
                | {
                    "code": "PENDING_IGST",
                    "name": "Pending IGST",
                    "group_id": str(group_id),
                    "kind": "GENERAL",
                },
            ),
            source(
                "journal_line",
                tax_line_id,
                expense_line.data
                | {"sequence": 3, "account_id": str(tax_id), "amount": "20", "base_amount": "20"},
            ),
            source(
                "invoice_tax_component",
                tax_component_id,
                {
                    "invoice_id": ids["invoice"],
                    "supply_id": ids["supply"],
                    "component_key": "IGST",
                    "code": "IGST",
                    "basis": "200",
                    "amount": "20",
                    "percentage": "10",
                    "supplier_charged": True,
                    "rounding_mode": "HALF_UP",
                    "source_version": 1,
                },
            ),
            source(
                "invoice_posting_line",
                uuid.uuid4(),
                {
                    "invoice_id": ids["invoice"],
                    "journal_line_id": str(tax_line_id),
                    "tax_component_id": str(tax_component_id),
                    "tax_purpose": "PENDING_IGST",
                    "line_key": str(uuid.uuid4()),
                    "sequence": 3,
                    "source_version": 1,
                    "purpose": "TAX",
                    "tracking": "NONE",
                    "bill_reference": None,
                    "due_date": None,
                },
            ),
        ]
    )
    return purchase, ids, invoice_journal, tax_id, tax_line_id, tax_component_id


def test_purchase_credit_register_distinguishes_pending_and_verified_tax():
    purchase, ids, invoice_journal, tax_id, tax_line_id, tax_component_id = purchase_dataset()
    reconcile(purchase, financial_manifest(purchase).control)
    request = RunRequest(
        code="INVOICE_CREDIT_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    pending = calculate(purchase, request, dt.date(2026, 4, 1))[0]
    assert len(pending) == 1 and pending[0]["pending"] == "20.0000"

    action_id = uuid.uuid4()
    purchase.extend(
        [
            source(
                "invoice_credit_action",
                action_id,
                {
                    "invoice_id": ids["invoice"],
                    "component_id": str(tax_component_id),
                    "expected_event_id": str(uuid.uuid4()),
                    "kind": "VERIFY",
                    "amount": "20",
                    "event_date": "2026-04-03",
                    "posting_date": "2026-04-03",
                    "currency": "INR",
                    "journal_id": None,
                    "offset_account_id": None,
                    "cash_deposit_line_id": None,
                    "annual_return_filed_on": None,
                    "document_verified": True,
                    "supply_received": True,
                    "business_use": True,
                    "restrictions_checked": True,
                    "supplier_report_matched": True,
                    "tax_payment_verified": True,
                    "return_filed": True,
                    "supplier_paid": True,
                    "reference": "supplier-evidence",
                    "evidence_sha256": "a" * 64,
                    "reason": "supplier and payment evidence verified",
                },
            ),
            source(
                "invoice_credit_event",
                uuid.uuid4(),
                {"invoice_id": ids["invoice"], "action_id": str(action_id)},
            ),
        ]
    )
    reconcile(purchase, financial_manifest(purchase).control)
    verified = calculate(purchase, request, dt.date(2026, 4, 1))[0]
    position = next(row for row in verified if row["row_kind"] == "CREDIT_POSITION")
    event = next(row for row in verified if row["row_kind"] == "CREDIT_EVENT")
    assert position["pending"] == "0.0000"
    assert position["eligible_unclaimed"] == "20.0000"
    assert event["event_amount"] == "20" and event["action"] == "VERIFY"

    claim_journal, eligible_account, claim_action = [uuid.uuid4() for _ in range(3)]
    tax_account = next(
        row for row in purchase if row.entity == "account" and row.source_id == tax_id
    )
    tax_line = next(
        row for row in purchase if row.entity == "journal_line" and row.source_id == tax_line_id
    )
    verify_action = next(
        row
        for row in purchase
        if row.entity == "invoice_credit_action" and row.source_id == action_id
    )
    purchase.extend(
        [
            source(
                "account",
                eligible_account,
                tax_account.data | {"code": "ELIGIBLE_IGST", "name": "Eligible IGST"},
            ),
            source(
                "journal",
                claim_journal,
                invoice_journal.data
                | {
                    "kind": "TAX_ACTION",
                    "number": "ITC-CLAIM-1",
                    "source_id": str(claim_journal),
                    "document_date": "2026-04-04",
                    "posting_date": "2026-04-04",
                    "total_debit": "10",
                    "total_credit": "10",
                },
            ),
            *[
                source(
                    "journal_line",
                    uuid.uuid4(),
                    tax_line.data
                    | {
                        "journal_id": str(claim_journal),
                        "sequence": sequence,
                        "account_id": str(account_id),
                        "side": side,
                        "amount": "10",
                        "base_amount": "10",
                    },
                )
                for sequence, account_id, side in (
                    (1, eligible_account, "DEBIT"),
                    (2, tax_id, "CREDIT"),
                )
            ],
            source(
                "invoice_credit_action",
                claim_action,
                verify_action.data
                | {
                    "expected_event_id": str(uuid.uuid4()),
                    "kind": "CLAIM",
                    "amount": "10",
                    "event_date": "2026-04-04",
                    "posting_date": "2026-04-04",
                    "journal_id": str(claim_journal),
                    "reference": "return-claim-1",
                },
            ),
            source(
                "invoice_credit_event",
                uuid.uuid4(),
                {"invoice_id": ids["invoice"], "action_id": str(claim_action)},
            ),
        ]
    )
    reconcile(purchase, financial_manifest(purchase).control)
    claimed = calculate(purchase, request, dt.date(2026, 4, 1))[0]
    claim_position = next(row for row in claimed if row["row_kind"] == "CREDIT_POSITION")
    assert claim_position["eligible_unclaimed"] == "10.0000"
    assert claim_position["claimed"] == "10.0000"
    tax_gl = calculate(
        purchase, request.model_copy(update={"code": "TAX_GL_BRIDGE"}), dt.date(2026, 4, 1)
    )[0]
    assert len(tax_gl) == 3
    assert {row["tax_purpose"] for row in tax_gl} == {"PENDING_IGST", "CLAIM"}


async def test_native_invoice_register_api_freezes_safe_export(client, prefix, app):
    for code, expected in (
        ("SALES_REGISTER", ["POSTING", "DOCUMENT"]),
        ("INVOICE_TAX_REGISTER", ["POSTING", "DOCUMENT", "TAX_POINT"]),
        ("INVOICE_CREDIT_REGISTER", ["POSTING"]),
    ):
        fields = await client.get(
            prefix + f"/report-definitions/{code}/field-set", headers=headers()
        )
        assert (
            fields.status_code == 200
            and fields.json()["native"]["properties"]["date_basis"]["enum"] == expected
        )
    fields = await client.get(
        prefix + "/report-definitions/TRIAL_BALANCE/field-set", headers=headers()
    )
    assert "date_basis" not in fields.json()["native"]["properties"]
    facts, ids = invoice_dataset()
    record = await generation(client, prefix)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await company_lock(db, TENANT, COMPANY)
            row = await get(db, COMPANY, m.ReportGeneration, uuid.UUID(record["id"]))
            manifest = financial_manifest(facts, identity=row.snapshot_id)
            bundle = await ingest.bundle(db, row, manifest)
            await ingest.stage(db, bundle, FactPage(manifest_id=manifest.id, items=facts), 0)
            await db.flush()
            await ingest.apply(db, row, bundle)
            await db.flush()
            row.target_sequence = row.applied_sequence
            await ingest.activate(db, row)
    body = {
        "code": "SALES_REGISTER",
        "generation_id": record["id"],
        "invoice_id": ids["invoice"],
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
    }
    key = headers()
    created = await client.post(prefix + "/report-runs", json=body, headers=key)
    assert created.status_code == 202, created.text
    identity = created.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await runs.complete(db, await get(db, COMPANY, m.ReportRun, uuid.UUID(identity)))
    assert (await client.post(prefix + "/report-runs", json=body, headers=key)).json()[
        "id"
    ] == identity
    result = await client.get(prefix + "/report-runs/" + identity, headers=headers())
    assert result.json()["evidence"]["invoice_coverage"] == "NATIVE_VOUCHER_INVOICES"
    downloaded = await client.get(
        prefix + "/report-runs/" + identity + "/download",
        headers=headers(),
        params={"token": result.json()["download_token"]},
    )
    assert downloaded.status_code == 200 and "INV-1" in downloaded.text
    denial = {
        "entity_type": "accounting.invoice_record",
        "field_key": "payable",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await client.get(
            prefix + "/report-runs/" + identity + "/rows", headers=headers(policies=[denial])
        )
    ).status_code == 403
