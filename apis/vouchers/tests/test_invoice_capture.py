"""Native reusable invoice capture, policy restrictions and historical isolation."""

import datetime as dt
import secrets
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, TENANT, headers
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from test_foundation import create_type, draft
from test_money_capture import project
from voucher_execution.invoice import (
    InvoiceCalculationDetail,
    InvoiceInput,
    InvoicePolicy,
    sales_policy_violation,
)
from voucher_execution.transport import ExecutionClient

from vouchers.domain.configuration import intersect, validate_policy
from vouchers.domain.documents import validate_content
from vouchers.domain.invoice import validate_invoice
from vouchers.models import core as m
from vouchers.models import invoice as i
from vouchers.schemas.configuration import Policy, SalesWorkflowConfiguration
from vouchers.schemas.documents import ReferenceInput, VoucherInput
from vouchers.schemas.owners import Owner


def invoice_body():
    supply = str(uuid7())
    first, second = str(uuid7()), str(uuid7())
    return {
        "party_line_key": str(uuid7()),
        "party_account_id": str(uuid7()),
        "party_account_version": 1,
        "bill_reference": "INV-1",
        "due_date": dt.date.today().isoformat(),
        "tax": {"profile": "UNTAXED_ACCOUNT"},
        "supplies": [
            {
                "line_key": supply,
                "account_id": str(uuid7()),
                "account_version": 1,
                "supply_kind": "SERVICE",
                "description": "Consulting service",
                "amount": "1000",
            }
        ],
        "components": [
            {
                "component_key": first,
                "purpose": "DISCOUNT",
                "scope": "LINE",
                "effect": "DEDUCT",
                "input_kind": "PERCENT",
                "value": "10.12345678",
                "targets": [supply],
                "source_evidence": "Approved trade terms",
            },
            {
                "component_key": second,
                "purpose": "DISCOUNT",
                "scope": "INVOICE",
                "effect": "DEDUCT",
                "input_kind": "PERCENT",
                "value": "5",
                "targets": [supply],
                "dependencies": [first],
                "source_evidence": "Invoice discount",
            },
        ],
    }


def test_sales_workflow_requires_order_evidence_and_bounds_due_date():
    today = dt.date.today()
    body = invoice_body()
    body["components"] = []
    body["due_date"] = (today + dt.timedelta(days=31)).isoformat()
    content = VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": today.isoformat(),
            "currency": "INR",
            "invoice": body,
        }
    )
    policy = Policy(
        schema_version=2,
        sales_workflow=SalesWorkflowConfiguration(
            max_due_days=30, customer_order_reference_required=True
        ),
    )
    with pytest.raises(ValidationFailedError, match="due date"):
        validate_content(
            content, policy, kind="SALES", profile="STANDARD", stage="DRAFT", today=today
        )
    body["due_date"] = (today - dt.timedelta(days=1)).isoformat()
    early = content.model_copy(update={"invoice": InvoiceInput.model_validate(body)})
    with pytest.raises(ValidationFailedError, match="due date"):
        validate_content(
            early, policy, kind="SALES", profile="STANDARD", stage="DRAFT", today=today
        )
    body["due_date"] = (today + dt.timedelta(days=30)).isoformat()
    content = content.model_copy(update={"invoice": InvoiceInput.model_validate(body)})
    validate_content(content, policy, kind="SALES", profile="STANDARD", stage="DRAFT", today=today)
    content = content.model_copy(update={
        "invoice": content.invoice.model_copy(update={"accepted_calculation_hash": "a" * 64})
    })
    with pytest.raises(ValidationFailedError, match="customer order"):
        validate_content(
            content, policy, kind="SALES", profile="STANDARD", stage="ISSUED", today=today
        )
    blank_reference = content.model_copy(
        update={"references": (ReferenceInput(purpose="CUSTOMER_ORDER", reference=" "),)}
    )
    with pytest.raises(ValidationFailedError, match="customer order"):
        validate_content(
            blank_reference,
            policy,
            kind="SALES",
            profile="STANDARD",
            stage="ISSUED",
            today=today,
        )
    content = content.model_copy(
        update={"references": (ReferenceInput(purpose="CUSTOMER_ORDER", reference="PO-42"),)}
    )
    validate_content(content, policy, kind="SALES", profile="STANDARD", stage="ISSUED", today=today)
    with pytest.raises(ValidationFailedError, match="Sales workflow"):
        validate_policy("PURCHASE", "STANDARD", policy)


async def seed_accounts(app, body):
    entries = [
        {"account_id": body["party_account_id"]},
        *body["supplies"],
        *body.get("tenders", []),
    ]
    await project(app, list({row["account_id"]: row for row in entries}.values()))


async def test_financial_note_requires_source_and_keeps_it_in_common_detail(client, prefix, app):
    kind = await create_type(client, prefix, kind="CREDIT_NOTE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    await seed_accounts(app, body)
    invalid = await client.post(
        prefix + "/vouchers",
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "posting_date": dt.date.today().isoformat(),
            "currency": "INR",
            "invoice": body,
        },
        headers=headers(),
    )
    assert invalid.status_code == 422
    source_id = str(uuid7())
    body["source_invoice_id"] = source_id
    created, _ = await draft(
        client,
        prefix,
        kind["revision_id"],
        invoice=body,
        posting_date=dt.date.today().isoformat(),
    )
    assert created["invoice"]["source_invoice_id"] == source_id
    detail = await client.get(prefix + "/vouchers/" + created["id"], headers=headers())
    assert detail.status_code == 200
    assert detail.json()["invoice"]["source_invoice_id"] == source_id


@pytest.mark.parametrize("voucher_kind", ["SALES", "CREDIT_NOTE"])
async def test_invoice_preview_uses_current_revision_and_owner_transport(
    client, prefix, app, monkeypatch, voucher_kind
):
    kind = await create_type(client, prefix, kind=voucher_kind, policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    if voucher_kind == "CREDIT_NOTE":
        body["source_invoice_id"] = str(uuid7())
    await seed_accounts(app, body)
    document, _ = await draft(
        client, prefix, kind["revision_id"], invoice=body, posting_date=dt.date.today().isoformat()
    )
    app.state.settings.execution_owner = Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="invoice-preview-test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    observed = []

    async def owner_preview(self, command):
        observed.append(command)
        return InvoiceCalculationDetail.model_validate(
            {
                "calculation_hash": "b" * 64,
                "currency": "INR",
                "commercial_total": "1000",
                "tax_total": "0",
                "charged_tax_total": "0",
                "rounding": "0",
                "payable": "1000",
                "lines": [
                    {
                        "key": body["supplies"][0]["line_key"],
                        "entered": "1000",
                        "commercial": "1000",
                        "taxable": "1000",
                        "taxes": [],
                        "price_rounding": "0",
                        "payable": "1000",
                    }
                ],
                "components": [],
                "allocations": [],
                "tax_evidence": [],
            }
        )

    monkeypatch.setattr(ExecutionClient, "preview", owner_preview)
    path = prefix + "/vouchers/" + document["id"] + "/invoice-preview"
    result = await client.post(path, json={"expected_version": 1}, headers=headers())
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json()["calculation_hash"] == "b" * 64
    assert str(observed[0].invoice.party_account_id) == body["party_account_id"]
    assert observed[0].configuration_hash == document["configuration_hash"]
    stale = await client.post(path, json={"expected_version": 2}, headers=headers())
    assert stale.status_code == 409
    assert len(observed) == 1
    acceptance = prefix + "/vouchers/" + document["id"] + "/invoice-acceptance"
    denied = await client.post(
        acceptance,
        json={"expected_version": 1, "calculation_hash": "b" * 64},
        headers=headers(
            policies=[
                {
                    "entity_type": "vouchers.voucher",
                    "field_key": "invoice",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        ),
    )
    assert denied.status_code == 403
    key = headers()
    accepted = await client.post(
        acceptance,
        json={"expected_version": 1, "calculation_hash": "b" * 64},
        headers=key,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["revision_id"] != document["revision_id"]
    assert accepted.json()["invoice"]["accepted_calculation_hash"] == "b" * 64
    assert accepted.json()["invoice"]["payable_total"] == "1000.0000"
    assert accepted.json()["invoice"]["supplies"] == document["invoice"]["supplies"]
    assert accepted.json()["narration"] == document["narration"]
    replay = await client.post(
        acceptance,
        json={"expected_version": 1, "calculation_hash": "b" * 64},
        headers=key,
    )
    assert replay.status_code == 200
    assert replay.json()["revision_id"] == accepted.json()["revision_id"]
    assert (
        await client.post(
            acceptance,
            json={"expected_version": 1, "calculation_hash": "c" * 64},
            headers=headers(),
        )
    ).status_code == 409


async def test_invoice_capture_native_roundtrip_history_and_masking(client, prefix, app):
    kind = await create_type(
        client, prefix, kind="SALES", policy={"invoice": {"manual_discounts_allowed": True}}
    )
    body = invoice_body()
    body["supplies"][0]["tax"] = {
        "profile": "INDIA_DOMESTIC_SERVICE",
        "company_registration_id": str(uuid7()),
        "place_of_supply": "IN-MH",
        "service_completion_date": "2026-03-31",
    }
    await seed_accounts(app, body)
    document, request = await draft(client, prefix, kind["revision_id"], invoice=body)
    assert document["kind"] == "SALES" and document["profile"] == "STANDARD"
    expected = InvoiceInput.model_validate(body).model_dump(mode="json")
    assert document["invoice"] == expected
    assert document["lines"] == []
    read = await client.get(prefix + "/vouchers/" + document["id"], headers=headers())
    assert read.json()["invoice"] == expected
    key = headers()
    created = await client.post(prefix + "/vouchers", headers=key, json=request)
    replayed = await client.post(prefix + "/vouchers", headers=key, json=request)
    assert created.status_code == replayed.status_code == 201
    assert created.json()["id"] == replayed.json()["id"]
    denied = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "invoice",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    masked = await client.get(
        prefix + "/vouchers/" + document["id"], headers=headers(policies=denied)
    )
    assert masked.status_code == 200 and masked.json().get("invoice") is None
    refused = await client.post(
        prefix + "/vouchers",
        json=request,
        headers=headers(policies=[denied[0] | {"access": "write"}]),
    )
    assert refused.status_code == 403
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revision = document["revision_id"]
            import uuid

            components = list(
                await db.scalars(
                    select(i.VoucherChargeDetail)
                    .where(i.VoucherChargeDetail.revision_id == uuid.UUID(revision))
                    .order_by(i.VoucherChargeDetail.sequence)
                )
            )
            assert (
                components[0].percentage == Decimal("10.12345678") and components[0].value is None
            )
            assert (
                len(
                    list(
                        await db.scalars(
                            select(i.VoucherChargeDependency).where(
                                i.VoucherChargeDependency.revision_id == uuid.UUID(revision)
                            )
                        )
                    )
                )
                == 1
            )
            assert {
                row.line_kind
                for row in await db.scalars(
                    select(m.VoucherLine).where(m.VoucherLine.revision_id == uuid.UUID(revision))
                )
            } == {"ACCOUNT", "CHARGE"}
            components[0].percentage = Decimal(20)
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()


async def test_invoice_settlements_reuse_tenders_and_bill_instructions(client, prefix, app):
    kind = await create_type(
        client, prefix, kind="PURCHASE", policy={"invoice": {"manual_discounts_allowed": True}}
    )
    body = invoice_body()
    line_key, account = str(uuid7()), str(uuid7())
    body["tenders"] = [
        {
            "account_id": account,
            "account_version": 1,
            "tender": {
                "tender_key": str(uuid7()),
                "line_key": line_key,
                "mode": "BANK_TRANSFER",
                "amount": "100",
                "currency": "INR",
                "reference": ref,
            },
        }
        for ref in ("ONE", "TWO")
    ]
    body["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"line_key": body["party_line_key"]},
            "credit": {"item_id": str(uuid7())},
            "amount": "50",
            "currency": "INR",
        }
    ]
    await seed_accounts(app, body)
    document, _ = await draft(client, prefix, kind["revision_id"], invoice=body)
    assert document["invoice"] == InvoiceInput.model_validate(body).model_dump(mode="json")
    assert document.get("financial") is None
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            account_entry = await db.scalar(select(m.VoucherAccountDetail))
            assert account_entry.amount == 200 and account_entry.side == "CREDIT"
            assert len(list(await db.scalars(select(m.VoucherTender)))) == 2
            assert len(list(await db.scalars(select(m.VoucherBillInstruction)))) == 1


async def test_invoice_stale_account_and_unconfigured_discount_rejected(client, prefix, app):
    kind = await create_type(client, prefix, kind="SALES")
    body = invoice_body()
    response = await client.post(
        prefix + "/vouchers",
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "invoice": body,
        },
        headers=headers(),
    )
    assert response.status_code == 422
    body["components"] = []
    await seed_accounts(app, body)
    body["party_account_version"] = 2
    response = await client.post(
        prefix + "/vouchers",
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "invoice": body,
        },
        headers=headers(),
    )
    assert response.status_code == 409


async def test_sales_configuration_restricts_account_tax_tender_and_component(client, prefix, app):
    body = invoice_body()
    body["components"] = []
    await seed_accounts(app, body)
    other_party = str(uuid7())
    await project(app, [{"account_id": other_party}])
    policy = {
        "invoice": {
            "sales_party_account_ids": [other_party],
            "sales_supply_account_ids": [body["supplies"][0]["account_id"]],
            "sales_tax_profiles": ["UNTAXED_ACCOUNT"],
            "sales_credit_allowed": False,
        }
    }
    kind = await create_type(client, prefix, kind="SALES", policy=policy)
    request = {
        "type_revision_id": kind["revision_id"],
        "document_date": dt.date.today().isoformat(),
        "currency": "INR",
        "invoice": body,
    }
    denied = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert denied.status_code == 422
    policy["invoice"]["sales_party_account_ids"] = [body["party_account_id"]]
    allowed = await create_type(client, prefix, code="SALE_ALLOWED", kind="SALES", policy=policy)
    request["type_revision_id"] = allowed["revision_id"]
    credit = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert credit.status_code == 422
    body["tenders"] = [
        {
            "account_id": str(uuid7()),
            "account_version": 1,
            "tender": {
                "tender_key": str(uuid7()),
                "line_key": str(uuid7()),
                "mode": "CASH",
                "amount": "1000",
                "currency": "INR",
            },
        }
    ]
    await project(app, [{"account_id": body["tenders"][0]["account_id"]}])
    request["invoice"] = body
    cash = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert cash.status_code == 201, cash.text


def test_sales_policy_controls_are_restrictive_and_legacy_wire_is_stable():
    from voucher_execution.invoice import (
        DISCOUNT_CONFIGURATION_FIELDS,
        SALES_CONFIGURATION_FIELDS,
        restrict_invoice,
    )

    assert InvoicePolicy().model_dump(mode="json") == InvoicePolicy.model_validate({}).model_dump(
        mode="json"
    )
    assert set(InvoicePolicy().model_dump(mode="json")) == (
        set(InvoicePolicy.model_fields) - SALES_CONFIGURATION_FIELDS - DISCOUNT_CONFIGURATION_FIELDS
    )
    restricted = restrict_invoice(
        InvoicePolicy(sales_party_account_ids=frozenset()),
        InvoicePolicy(sales_party_account_ids=frozenset({uuid7()})),
    )
    assert restricted.sales_party_account_ids == frozenset()
    body = invoice_body()
    body["components"] = []
    invoice = InvoiceInput.model_validate(body)
    assert sales_policy_violation(invoice, InvoicePolicy(sales_party_account_ids=frozenset()))
    assert sales_policy_violation(invoice, InvoicePolicy(sales_supply_account_ids=frozenset()))
    assert sales_policy_violation(invoice, InvoicePolicy(sales_tax_profiles=frozenset()))
    assert sales_policy_violation(invoice, InvoicePolicy(sales_credit_allowed=False))
    body["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"line_key": body["party_line_key"]},
            "credit": {"item_id": str(uuid7())},
            "amount": "10",
            "currency": "INR",
        }
    ]
    invoice = InvoiceInput.model_validate(body)
    assert sales_policy_violation(invoice, InvoicePolicy(sales_advance_adjustments_allowed=False))
    body["allocations"] = []
    body["tenders"] = [
        {
            "account_id": str(uuid7()),
            "account_version": 1,
            "tender": {
                "tender_key": str(uuid7()),
                "line_key": str(uuid7()),
                "mode": "CASH",
                "amount": "10",
                "currency": "INR",
            },
        }
        for _ in range(2)
    ]
    invoice = InvoiceInput.model_validate(body)
    assert sales_policy_violation(invoice, InvoicePolicy(sales_tender_modes=frozenset()))
    assert sales_policy_violation(invoice, InvoicePolicy(sales_split_tenders_allowed=False))
    body["tenders"] = []
    body["rounding_increment"] = "1"
    body["rounding_account_id"] = str(uuid7())
    body["rounding_account_version"] = 1
    invoice = InvoiceInput.model_validate(body)
    assert sales_policy_violation(invoice, InvoicePolicy(sales_invoice_rounding_allowed=False))
    body.pop("rounding_increment")
    body.pop("rounding_account_id")
    body.pop("rounding_account_version")
    body["components"] = invoice_body()["components"]
    # Component targets must match the invoice supply identity.
    body["components"] = [body["components"][0] | {"targets": [body["supplies"][0]["line_key"]]}]
    invoice = InvoiceInput.model_validate(body)
    assert sales_policy_violation(invoice, InvoicePolicy(sales_discount_scopes=frozenset()))
    body["components"][0]["purpose"] = "FREIGHT"
    body["components"][0]["effect"] = "ADD"
    invoice = InvoiceInput.model_validate(body)
    assert sales_policy_violation(invoice, InvoicePolicy(sales_charge_scopes=frozenset()))


async def test_sales_only_configuration_cannot_be_bound_to_purchase_or_common(client, prefix):
    invoice = {"sales_credit_allowed": False}
    purchase = await client.post(
        prefix + "/voucher-types",
        json={
            "code": "PURCHASE_SALES_RULE",
            "name": "Invalid purchase policy",
            "kind": "PURCHASE",
            "policy": {"invoice": invoice},
        },
        headers=headers(),
    )
    assert purchase.status_code == 422
    common = await client.post(
        prefix + "/voucher-configurations",
        json={
            "code": "COMMON_SALES_RULE",
            "name": "Invalid common policy",
            "family": "COMMON",
            "policy": {"invoice": invoice},
        },
        headers=headers(),
    )
    assert common.status_code == 422
    sales = await client.post(
        prefix + "/voucher-configurations",
        json={
            "code": "SALES_RULE",
            "name": "Sales policy",
            "family": "SALES",
            "policy": {"invoice": invoice},
        },
        headers=headers(),
    )
    assert sales.status_code == 201, sales.text
    impossible = await client.post(
        prefix + "/voucher-configurations",
        json={
            "code": "SALES_IMPOSSIBLE",
            "name": "Impossible Sales policy",
            "family": "SALES",
            "policy": {"invoice": {"sales_tax_profiles": []}},
        },
        headers=headers(),
    )
    assert impossible.status_code == 422


async def test_v2_sales_pro_forma_cannot_publish_unexecutable_invoice_controls(client, prefix):
    response = await client.post(
        prefix + "/voucher-types",
        json={
            "code": "PRO_FORMA_INVOICE_POLICY",
            "name": "Pro forma invoice policy",
            "kind": "SALES",
            "profile": "PRO_FORMA",
            "policy": {"schema_version": 2, "invoice": {"sales_credit_allowed": False}},
        },
        headers=headers(),
    )
    assert response.status_code == 422, response.text


async def test_sales_account_allowlist_requires_current_company_master(client, prefix):
    response = await client.post(
        prefix + "/voucher-types",
        json={
            "code": "UNAVAILABLE_SALES_ACCOUNT",
            "name": "Unavailable Sales account",
            "kind": "SALES",
            "policy": {"invoice": {"sales_supply_account_ids": [str(uuid7())]}},
        },
        headers=headers(),
    )
    assert response.status_code == 422


async def test_sales_account_allowlist_cannot_reference_other_company(client, prefix, app):
    from vouchers.schemas.sources import SourceBundle
    from vouchers.tasks.sources import apply_bundle

    other_account = uuid7()
    bundle = SourceBundle.model_validate(
        {
            "message_id": str(uuid7()),
            "tenant_id": str(TENANT),
            "company_id": str(uuid7()),
            "masters": [
                {
                    "entity_type": "account",
                    "source_id": str(other_account),
                    "source_version": 1,
                    "status": "ACTIVE",
                    "facts": {"kind": "GENERAL"},
                }
            ],
        }
    )
    await apply_bundle(app.state.session_factory, bundle, "accounting")
    response = await client.post(
        prefix + "/voucher-types",
        json={
            "code": "FOREIGN_SALES_ACCOUNT",
            "name": "Foreign Sales account",
            "kind": "SALES",
            "policy": {"invoice": {"sales_supply_account_ids": [str(other_account)]}},
        },
        headers=headers(),
    )
    assert response.status_code == 422


async def test_bound_sales_family_policy_is_enforced_for_company(client, prefix, app):
    body = invoice_body()
    body["components"] = []
    await seed_accounts(app, body)
    config = (
        await client.post(
            prefix + "/voucher-configurations",
            headers=headers(),
            json={
                "code": "CASH_SALES",
                "name": "Cash Sales policy",
                "family": "SALES",
                "policy": {"invoice": {"sales_credit_allowed": False}},
            },
        )
    ).json()
    published = await client.post(
        prefix + "/voucher-configurations/" + config["id"] + "/publish",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 2,
            "configuration_revision_id": config["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    kind = await create_type(client, prefix, kind="SALES", policy={"invoice": {}})
    effective = await client.get(
        prefix + "/voucher-types/" + kind["id"] + "/effective-configuration",
        params={"date": dt.date.today().isoformat()},
        headers=headers(),
    )
    assert effective.status_code == 200, effective.text
    assert effective.json()["policy"]["invoice"]["sales_credit_allowed"] is False
    document = await client.post(
        prefix + "/vouchers",
        headers=headers(),
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "invoice": body,
        },
    )
    assert document.status_code == 422


async def test_separate_tax_targets_roundtrip_and_policy(client, prefix, app):
    body = invoice_body()
    first = body["supplies"][0]
    second = first | {"line_key": str(uuid7()), "amount": "500"}
    body["supplies"].append(second)
    body["components"] = [
        body["components"][0]
        | {
            "tax_targets": [second["line_key"]],
            "tax_allocation_basis": "VALUE",
        }
    ]
    await seed_accounts(app, body)
    kind = await create_type(
        client, prefix, kind="SALES", policy={"invoice": {"manual_discounts_allowed": True}}
    )
    request = {
        "type_revision_id": kind["revision_id"],
        "document_date": dt.date.today().isoformat(),
        "currency": "INR",
        "invoice": body,
    }
    rejected = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert rejected.status_code == 422 and "not configured" in rejected.text
    enabled = await create_type(
        client,
        prefix,
        code="SEPARATE_TAX",
        kind="SALES",
        policy={
            "invoice": {
                "manual_discounts_allowed": True,
                "independent_tax_allocation_allowed": True,
            }
        },
    )
    created = await client.post(
        prefix + "/vouchers",
        json=request | {"type_revision_id": enabled["revision_id"]},
        headers=headers(),
    )
    assert created.status_code == 201, created.text
    assert created.json()["invoice"] == InvoiceInput.model_validate(body).model_dump(mode="json")
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            targets = list(await db.scalars(select(i.VoucherChargeTarget)))
            assert {t.purpose for t in targets} == {"BASIS", "TAX_BASE"}
            assert len({t.supply_id for t in targets}) == 2
    body["components"][0]["tax_targets"] = [str(uuid7())]
    with pytest.raises(ValidationError, match="within the invoice"):
        InvoiceInput.model_validate(body)


def test_invoice_policy_cannot_widen_and_old_content_is_stable():
    parent = Policy(invoice=InvoicePolicy(max_components=1))
    child = Policy(invoice=InvoicePolicy(manual_discounts_allowed=True, max_components=10))
    merged = intersect(parent, child)
    assert merged.invoice.max_components == 1 and not merged.invoice.manual_discounts_allowed
    assert "invoice" not in Policy().model_dump(mode="json")
    body = VoucherInput(type_revision_id=uuid7(), document_date=dt.date.today(), currency="INR")
    assert "invoice" not in body.model_dump(mode="json")


def test_discount_configuration_restricts_both_sales_and_purchase_capture():
    body = invoice_body()
    invalid = invoice_body()
    invalid["components"][0]["commercial_treatment"] = "THIRD_PARTY_COST"
    invalid["components"][0]["cost_targets"] = [invalid["supplies"][0]["line_key"]]
    with pytest.raises(ValidationError, match="counterparty consideration"):
        InvoiceInput.model_validate(invalid)
    content = VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "invoice": body,
        }
    )
    parent = InvoicePolicy(
        manual_discounts_allowed=True,
        discount_input_kinds=frozenset({"PERCENT"}),
        max_discount_pct=Decimal(12),
        max_discount_amount=Decimal(120),
        max_discount_components=2,
        discount_compounding_allowed=False,
    )
    child = InvoicePolicy(
        manual_discounts_allowed=True,
        max_discount_pct=Decimal(50),
        max_discount_amount=Decimal(300),
    )
    effective = intersect(Policy(invoice=parent), Policy(invoice=child)).invoice
    assert effective is not None
    assert effective.max_discount_pct == 12
    assert effective.max_discount_amount == 120
    assert not effective.discount_compounding_allowed
    for kind in ("SALES", "PURCHASE"):
        with pytest.raises(ValidationFailedError, match="compounding"):
            validate_invoice(content, effective, kind=kind, profile="STANDARD")
    charge = body["components"][1] | {
        "purpose": "OTHER_CHARGE",
        "effect": "ADD",
    }
    later_discount = body["components"][1] | {
        "component_key": str(uuid7()),
        "dependencies": [charge["component_key"]],
    }
    indirect = content.model_copy(
        update={
            "invoice": InvoiceInput.model_validate(
                body | {"components": [body["components"][0], charge, later_discount]}
            )
        }
    )
    with pytest.raises(ValidationFailedError, match="compounding"):
        validate_invoice(
            indirect,
            effective.model_copy(update={"charges_allowed": True, "max_discount_components": 3}),
            kind="PURCHASE",
            profile="STANDARD",
        )
    no_compounding = content.model_copy(
        update={
            "invoice": content.invoice.model_copy(
                update={"components": (content.invoice.components[0],)}
            )
        }
    )
    validate_invoice(no_compounding, effective, kind="PURCHASE", profile="STANDARD")
    fixed = no_compounding.model_copy(
        update={
            "invoice": no_compounding.invoice.model_copy(
                update={
                    "components": (
                        no_compounding.invoice.components[0].model_copy(
                            update={"input_kind": "FIXED"}
                        ),
                    )
                }
            )
        }
    )
    with pytest.raises(ValidationFailedError, match="input kind"):
        validate_invoice(fixed, effective, kind="SALES", profile="STANDARD")
    with pytest.raises(ValidationFailedError, match="viable discount"):
        validate_policy(
            "PURCHASE",
            "STANDARD",
            Policy(
                invoice=InvoicePolicy(
                    manual_discounts_allowed=True, discount_input_kinds=frozenset()
                )
            ),
        )


async def test_published_discount_configuration_is_enforced_on_voucher_create(client, prefix, app):
    body = invoice_body()
    await seed_accounts(app, body)
    kind = await create_type(
        client,
        prefix,
        kind="SALES",
        policy={
            "invoice": {
                "manual_discounts_allowed": True,
                "discount_input_kinds": ["PERCENT"],
                "max_discount_components": 1,
            }
        },
    )
    request = {
        "type_revision_id": kind["revision_id"],
        "document_date": dt.date.today().isoformat(),
        "currency": "INR",
        "invoice": body,
    }
    too_many = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert too_many.status_code == 422 and "discount component limit" in too_many.text
    body["components"] = [body["components"][0] | {"input_kind": "FIXED", "value": "10"}]
    fixed = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert fixed.status_code == 422 and "discount input kind" in fixed.text
    body["components"][0]["input_kind"] = "PERCENT"
    accepted = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert accepted.status_code == 201, accepted.text


async def test_invoice_submit_requires_accepted_calculation(client, prefix, app):
    body = invoice_body()
    body["components"] = []
    await seed_accounts(app, body)
    kind = await create_type(client, prefix, kind="SALES", policy={"invoice": {}})
    document, _ = await draft(
        client, prefix, kind["revision_id"], invoice=body, posting_date=dt.date.today().isoformat()
    )
    result = await client.post(
        prefix + "/vouchers/" + document["id"] + "/submit",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert result.status_code == 422
    assert "calculation must be accepted" in result.text


def test_invoice_cycles_cross_targets_and_split_account_conflicts():
    body = invoice_body()
    body["components"][0]["dependencies"] = [body["components"][1]["component_key"]]
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(body),
    )
    with pytest.raises(ValidationFailedError, match="cycle"):
        validate_invoice(
            content, InvoicePolicy(manual_discounts_allowed=True), kind="SALES", profile="STANDARD"
        )
    body["components"][0]["targets"] = [str(uuid7())]
    with pytest.raises(ValidationError, match="within the invoice"):
        InvoiceInput.model_validate(body)


@pytest.mark.parametrize(
    "actual,billed,different_unit",
    [("11", "10", False), ("10", "10", True)],
)
def test_invoice_capture_rejects_conflicting_ordinary_quantity_evidence(
    actual, billed, different_unit
):
    body = invoice_body()
    body["components"] = []
    unit = str(uuid7())
    body["supplies"][0]["quantities"] = [
        {"basis": "ACTUAL", "quantity": actual, "unit_id": unit},
        {
            "basis": "BILLED",
            "quantity": billed,
            "unit_id": str(uuid7()) if different_unit else unit,
        },
    ]
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(body),
    )
    with pytest.raises(ValidationFailedError, match="inconsistent"):
        validate_invoice(content, InvoicePolicy(), kind="SALES", profile="STANDARD")


@pytest.mark.parametrize(
    "actual,billed",
    [("10", "11"), ("11", None), ("11", "11")],
)
def test_manual_paid_bundle_requires_disjoint_positive_quantity_roles(actual, billed):
    body = invoice_body()
    body["components"] = []
    unit = str(uuid7())
    body["supplies"][0].update(
        free_purpose="MANUAL_PAID_BUNDLE",
        free_reason="Agreed bonus service units",
        quantities=[
            {"basis": "ACTUAL", "quantity": actual, "unit_id": unit},
            *(
                [{"basis": "BILLED", "quantity": billed, "unit_id": unit}]
                if billed is not None
                else []
            ),
        ],
    )
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(body),
    )
    with pytest.raises(ValidationFailedError, match="positive reward"):
        validate_invoice(
            content,
            InvoicePolicy(manual_free_allowed=True),
            kind="SALES",
            profile="STANDARD",
        )


def test_manual_paid_bundle_accepts_explicit_disjoint_quantity_roles():
    body = invoice_body()
    body["components"] = []
    unit = str(uuid7())
    body["supplies"][0].update(
        free_purpose="MANUAL_PAID_BUNDLE",
        free_reason="Agreed bonus service unit",
        quantities=[
            {"basis": "ACTUAL", "quantity": "11", "unit_id": unit},
            {"basis": "BILLED", "quantity": "10", "unit_id": unit},
        ],
    )
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(body),
    )
    validate_invoice(
        content,
        InvoicePolicy(manual_free_allowed=True),
        kind="SALES",
        profile="STANDARD",
    )
    with pytest.raises(ValidationFailedError, match="execution is not available"):
        validate_invoice(
            content,
            InvoicePolicy(manual_free_allowed=True),
            kind="SALES",
            profile="STANDARD",
            stage="SUBMITTED",
        )
    with pytest.raises(ValidationFailedError, match="execution is not available"):
        validate_content(
            content,
            Policy(invoice=InvoicePolicy(manual_free_allowed=True)),
            kind="SALES",
            profile="STANDARD",
            stage="SUBMITTED",
            today=dt.date.today(),
        )


def test_invoice_requires_accepted_calculation_before_submission():
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(invoice_body()),
    )
    policy = Policy(invoice=InvoicePolicy(manual_discounts_allowed=True))
    validate_content(
        content, policy, kind="SALES", profile="STANDARD", stage="DRAFT", today=dt.date.today()
    )
    with pytest.raises(ValidationFailedError, match="calculation must be accepted"):
        validate_content(
            content,
            policy,
            kind="SALES",
            profile="STANDARD",
            stage="SUBMITTED",
            today=dt.date.today(),
        )


@pytest.mark.parametrize(
    "policy,expected",
    [
        (InvoicePolicy(max_components=1), "component limit"),
        (InvoicePolicy(allowed_supply_kinds=frozenset({"ACCOUNT"})), "supply kind"),
        (
            InvoicePolicy(allowed_scopes=frozenset({"LINE"}), manual_discounts_allowed=True),
            "component recipe",
        ),
        (InvoicePolicy(allowed_component_inputs=frozenset({"FIXED"})), "component recipe"),
        (InvoicePolicy(), "manual discounts"),
        (InvoicePolicy(manual_discounts_allowed=True, max_allocations=1), "allocation limit"),
    ],
)
def test_invoice_configuration_enforces_commercial_limits(policy, expected):
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(invoice_body()),
    )
    with pytest.raises(ValidationFailedError, match=expected):
        validate_invoice(content, policy, kind="SALES", profile="STANDARD")


def test_invoice_configuration_blocks_unsupported_profile_and_charge():
    body = invoice_body()
    body["components"] = []
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(body),
    )
    with pytest.raises(ValidationFailedError, match="unavailable"):
        validate_invoice(content, InvoicePolicy(), kind="SALES", profile="UNSUPPORTED")
    body["components"] = [
        {
            "component_key": str(uuid7()),
            "purpose": "FREIGHT",
            "scope": "LINE",
            "effect": "ADD",
            "input_kind": "FIXED",
            "value": "15",
            "targets": [body["supplies"][0]["line_key"]],
            "source_evidence": "Delivery charge",
        }
    ]
    content = content.model_copy(update={"invoice": InvoiceInput.model_validate(body)})
    with pytest.raises(ValidationFailedError, match="charges"):
        validate_invoice(content, InvoicePolicy(), kind="SALES", profile="STANDARD")


@pytest.mark.parametrize(
    "actual,billed,unit_matches,expected",
    [
        ("2", "2", True, None),
        ("3", "2", True, "must match common item evidence"),
        ("2", "2", False, "must match common item evidence"),
    ],
)
def test_invoice_item_quantities_reconcile_with_common_item(actual, billed, unit_matches, expected):
    body = invoice_body()
    body["components"] = []
    line_key, unit_id = uuid7(), uuid7()
    body["supplies"][0].update(
        line_key=str(line_key),
        supply_kind="GOODS",
        item_line_key=str(line_key),
        quantities=[
            {"basis": "ACTUAL", "quantity": actual, "unit_id": str(unit_id)},
            {"basis": "BILLED", "quantity": billed, "unit_id": str(unit_id)},
        ],
    )
    content = VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "invoice": body,
            "lines": [
                {
                    "line_key": str(line_key),
                    "item": {
                        "item_id": str(uuid7()),
                        "item_version": 1,
                        "unit_id": str(unit_id if unit_matches else uuid7()),
                        "actual_quantity": "2",
                        "billed_quantity": "2",
                    },
                }
            ],
        }
    )
    if expected is None:
        validate_invoice(content, InvoicePolicy(), kind="SALES", profile="STANDARD")
    else:
        with pytest.raises(ValidationFailedError, match=expected):
            validate_invoice(content, InvoicePolicy(), kind="SALES", profile="STANDARD")


def test_invoice_configuration_requires_tax_allocation_permission_and_currency_match():
    body = invoice_body()
    body["components"][0]["tax_targets"] = [body["supplies"][0]["line_key"]]
    content = VoucherInput(
        type_revision_id=uuid7(),
        document_date=dt.date.today(),
        currency="INR",
        invoice=InvoiceInput.model_validate(body),
    )
    with pytest.raises(ValidationFailedError, match="independent tax allocation"):
        validate_invoice(
            content,
            InvoicePolicy(manual_discounts_allowed=True),
            kind="SALES",
            profile="STANDARD",
        )
    body["components"] = []
    body["tenders"] = [
        {
            "account_id": str(uuid7()),
            "account_version": 1,
            "tender": {
                "tender_key": str(uuid7()),
                "line_key": str(uuid7()),
                "mode": "CASH",
                "amount": "100",
                "currency": "USD",
            },
        }
    ]
    content = content.model_copy(update={"invoice": InvoiceInput.model_validate(body)})
    with pytest.raises(ValidationFailedError, match="invoice currency"):
        validate_invoice(content, InvoicePolicy(), kind="SALES", profile="STANDARD")


def test_invoice_configuration_checks_item_line_membership_and_empty_entry():
    empty = VoucherInput(type_revision_id=uuid7(), document_date=dt.date.today(), currency="INR")
    validate_invoice(empty, InvoicePolicy(), kind="SALES", profile="STANDARD")
    body = invoice_body()
    body["components"] = []
    identity = uuid7()
    body["supplies"][0].update(
        line_key=str(identity), item_line_key=str(identity), supply_kind="GOODS"
    )
    content = empty.model_copy(update={"invoice": InvoiceInput.model_validate(body)})
    with pytest.raises(ValidationFailedError, match="common item line"):
        validate_invoice(content, InvoicePolicy(), kind="SALES", profile="STANDARD")
