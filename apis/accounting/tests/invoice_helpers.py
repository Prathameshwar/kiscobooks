"""Post a purchase through the real invoice preview and durable execution boundaries."""

import hashlib

from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import select
from voucher_execution.invoice import InvoicePreviewCommand

from accounting.models.invoice import InvoiceRecord, InvoiceTaxComponent
from accounting.models.masters import AccountTaxDefault
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_invoice_preview import authority, connection
from tests.test_openings_sources import party_accounts
from tests.test_tax_mappings import register
from tests.test_voucher_execution import command
from tests.test_voucher_money import delegated
from tests.test_voucher_tax import (
    MH,
    SERVICE_PURCHASE,
    START,
    account,
    purchase,
    send,
    tax_head,
    world,
)


async def posted_purchase(client, app, *, reverse=False, components=False):
    data = await world(client, app)
    party, _, supplier = await party_accounts(client)
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
    expense = data["rcm"]
    if not reverse:
        expense = await account(client, data["groups"]["PURCHASES"], "FORWARD_SERVICE")
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                default = await db.scalar(
                    select(AccountTaxDefault).where(AccountTaxDefault.rcm_applicable.is_(True))
                )
                rule = default.rule_id
        await send(
            client,
            "/account-tax-defaults",
            purchase(expense["id"], rule, **(SERVICE_PURCHASE | {"rcm_applicable": False})),
        )
    data["pending"] = await tax_head(client, data["groups"], "PENDING_IGST", MH)
    authority_for_preview, company = authority(registrations=[MH])
    invoice = {
        "party_line_key": str(uuid7()),
        "party_account_id": supplier["id"],
        "party_account_version": supplier["row_version"],
        "bill_reference": "PURCHASE-CREDIT-1",
        "due_date": "2026-04-30",
        "tax": {
            "profile": "INDIA_DOMESTIC_SERVICE_RCM" if reverse else "INDIA_DOMESTIC_SERVICE",
            "company_registration_id": MH["id"],
            "party_registration_id": gstin.json()["id"],
            "place_of_supply": "IN-MH",
            "service_completion_date": "2026-04-01",
            "supplier_invoice_date": "2026-04-01",
            "supplier_invoice_number": "SUP-CREDIT-1",
        },
        "supplies": [
            {
                "line_key": str(uuid7()),
                "account_id": expense["id"],
                "account_version": expense["row_version"],
                "supply_kind": "SERVICE",
                "description": "Service",
                "amount": "1000",
            }
        ],
    }
    invoice_policy = {}
    if components:
        invoice_policy = {"manual_discounts_allowed": True, "charges_allowed": True}
        invoice["components"] = [
            {
                "component_key": str(uuid7()),
                "purpose": purpose,
                "scope": "LINE",
                "effect": effect,
                "input_kind": "FIXED",
                "value": "10",
                "targets": [invoice["supplies"][0]["line_key"]],
                "source_evidence": "Agreed trade terms",
            }
            for purpose, effect in (("DISCOUNT", "DEDUCT"), ("OTHER_CHARGE", "ADD"))
        ]
    evidence = {
        "kind": "PURCHASE",
        "profile": "STANDARD",
        "company_configuration_hash": company.finance.configuration_hash,
        "policy": {"invoice": invoice_policy},
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    calculated = await connection(client, app).preview(
        InvoicePreviewCommand.model_validate(
            {
                "tenant_id": TENANT,
                "company_id": COMPANY,
                "actor_user_id": USER,
                "authority": authority_for_preview,
                "kind": "PURCHASE",
                "currency": "INR",
                "document_date": "2026-04-02",
                "posting_date": "2026-04-02",
                "invoice": invoice,
                "policy": invoice_policy,
                "configuration_hash": digest,
                "company_configuration_hash": company.finance.configuration_hash,
            }
        )
    )
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
        kind="PURCHASE",
        source_payload=source,
        content_hash=hashlib.sha256(canonical_json(source)).hexdigest(),
        configuration_hash=digest,
        configuration_evidence=evidence | {"digest": digest},
        authority=delegated(registrations=[MH]),
    )
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
            data["invoice"] = await db.scalar(select(InvoiceRecord))
            data["component"] = await db.scalar(select(InvoiceTaxComponent))
    data["expense"] = expense
    return data
