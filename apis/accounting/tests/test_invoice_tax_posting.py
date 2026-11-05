"""Statutory invoice components persist natively and RCM never grants immediate ITC."""

import hashlib
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import select
from voucher_execution.invoice import InvoicePreviewCommand

from accounting.models.invoice import InvoiceRecord, InvoiceSupplyFact, InvoiceTaxComponent
from accounting.models.ledger import JournalLine
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_invoice_preview import authority, connection
from tests.test_openings_sources import party_accounts
from tests.test_tax_mappings import register
from tests.test_voucher_execution import command
from tests.test_voucher_money import delegated
from tests.test_voucher_tax import MH, START, tax_head, world


@pytest.mark.parametrize(
    "kind,expense", [("SALES", "income"), ("PURCHASE", "rcm"), ("PURCHASE", "blocked")]
)
async def test_gst_invoice_native_component_postings(client, app, kind, expense):
    data = await world(client, app)
    party, customer, supplier = await party_accounts(client)
    gstin = await register(
        client,
        party["id"],
        {
            "registration_type": "REGULAR",
            "registration_number": "24ABCDE1234F1Z6",
            "state_code": "IN-GJ",
            "valid_from": START,
        },
    )
    assert gstin.status_code == 201, gstin.text
    pending = await tax_head(client, data["groups"], "PENDING_IGST", MH)
    party_account = customer if kind == "SALES" else supplier
    tax = {
        "profile": "INDIA_DOMESTIC_SERVICE" if kind == "SALES" else "INDIA_DOMESTIC_SERVICE_RCM",
        "company_registration_id": MH["id"],
        "party_registration_id": gstin.json()["id"],
        "place_of_supply": "IN-GJ" if kind == "SALES" else "IN-MH",
        "service_completion_date": "2026-04-01",
        "supplier_invoice_date": "2026-04-01" if kind == "PURCHASE" else None,
        "supplier_invoice_number": "SUP-TEST" if kind == "PURCHASE" else None,
    }
    invoice = {
        "party_line_key": str(uuid7()),
        "party_account_id": party_account["id"],
        "party_account_version": party_account["row_version"],
        "bill_reference": "SERVICE-1",
        "due_date": "2026-04-30",
        "tax": tax,
        "supplies": [
            {
                "line_key": str(uuid7()),
                "account_id": data[expense]["id"],
                "account_version": data[expense]["row_version"],
                "supply_kind": "SERVICE",
                "description": "Service",
                "amount": "1000",
            }
        ],
    }
    policy = {"invoice": {}}
    evidence = {
        "kind": kind,
        "profile": "STANDARD",
        "company_configuration_hash": "a" * 64,
        "policy": policy,
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    preview_authority, _ = authority(registrations=[MH])
    preview_request = InvoicePreviewCommand.model_validate(
        {
            "tenant_id": TENANT,
            "company_id": COMPANY,
            "actor_user_id": USER,
            "authority": preview_authority,
            "kind": kind,
            "currency": "INR",
            "document_date": "2026-04-02",
            "posting_date": "2026-04-02",
            "invoice": invoice,
            "policy": {},
            "configuration_hash": digest,
            "company_configuration_hash": "a" * 64,
        }
    )
    calculated = await connection(client, app).preview(preview_request)
    invoice["accepted_calculation_hash"] = calculated.calculation_hash
    source = {
        "mode": "ACCOUNTS",
        "currency": "INR",
        "document_date": "2026-04-02",
        "posting_date": "2026-04-02",
        "lines": [],
        "invoice": invoice,
    }
    body = command(
        data["period"],
        protocol_version=2,
        kind=kind,
        source_payload=source,
        content_hash=hashlib.sha256(canonical_json(source)).hexdigest(),
        configuration_hash=digest,
        configuration_evidence=evidence | {"digest": digest},
        authority=delegated(registrations=[MH]),
    )
    from accounting.tasks.invoice_calculation import preview
    from accounting.tasks.invoice_execution import request_for
    from accounting.tasks.voucher_money_execution import authority as posting_authority

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            recalculated = await preview(
                db, posting_authority(body, SECRET.encode()), request_for(body), posting=True
            )
    assert recalculated == calculated
    result = await dispatch(
        app.state.session_factory,
        body,
        secret=SECRET.encode(),
        client=data["authority"],
        invoices_enabled=True,
    )
    assert result.outcome == "COMMITTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            record = await db.scalar(select(InvoiceRecord))
            supply = await db.scalar(select(InvoiceSupplyFact))
            component = await db.scalar(select(InvoiceTaxComponent))
            lines = list(await db.scalars(select(JournalLine)))
            assert record.tax_total == component.amount == Decimal("180")
            assert component.code == "IGST" and component.percentage == 18
            if kind == "SALES":
                assert record.payable == 1180 and component.supplier_charged
                assert supply.credit_state == "NOT_APPLICABLE"
                assert any(
                    row.account_id == uuid.UUID(data["heads"]["OUTPUT_IGST"]["id"])
                    and row.side == "CREDIT"
                    and row.amount == 180
                    for row in lines
                )
            else:
                assert record.payable == 1000 and not component.supplier_charged
                assert supply.tax_point_date.isoformat() == "2026-06-01"
                assert not any(
                    row.account_id == uuid.UUID(data["heads"]["INPUT_IGST"]["id"]) for row in lines
                )
                assert any(
                    row.account_id == uuid.UUID(data["heads"]["RCM_IGST"]["id"])
                    and row.side == "CREDIT"
                    and row.amount == 180
                    for row in lines
                )
                if expense == "rcm":
                    assert supply.credit_state == "PENDING_EVIDENCE"
                    assert any(
                        row.account_id == uuid.UUID(pending["id"])
                        and row.side == "DEBIT"
                        and row.amount == 180
                        for row in lines
                    )
                else:
                    assert supply.credit_state == "INELIGIBLE"
                    assert not any(row.account_id == uuid.UUID(pending["id"]) for row in lines)
