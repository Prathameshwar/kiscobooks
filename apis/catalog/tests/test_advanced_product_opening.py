"""Per-SKU opening decisions, retained owner commands and uncertain recovery."""

import datetime as dt
import time
import uuid
from decimal import Decimal
from typing import cast

import pytest
from billing_platform.company_context import CompanyContext, FinancialContext, sign_company_context
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from pydantic import ValidationError

from catalog.domain.attributes import AttributeValue
from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.attributes import AttributeOption
from catalog.models.products import Item, ProductFamily
from catalog.schemas.advanced_product_creation import AdvancedOpeningInput
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks import advanced_creation_opening as opening_tasks
from catalog.tasks.simple_creation_steps import opening_preflight
from catalog.tasks.simple_creation_transport import (
    CreationOwners,
    OwnerRejectedError,
    ServiceUnavailableError,
)
from tests.attribute_factories import seed_attributes
from tests.conftest import ACTOR_SECRET
from tests.test_advanced_product_definition import prepared
from tests.test_advanced_product_setup import definition
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_pending_stock_confirmation_explains_product_creation_options():
    class PendingOwner:
        async def call(self, service, method, path, body=None, key=None):
            assert service == "accounting" and path.endswith("/stock/openings/readiness")
            return {"blockers": ["EXECUTION_UNCONFIRMED"]}

    with pytest.raises(ConflictError, match="Save the product without opening stock"):
        await opening_preflight(cast(CreationOwners, PendingOwner()), uuid7(), "2026-04-01")


def test_stock_definition_fence_keeps_the_product_command_for_retry():
    temporary = OwnerRejectedError(
        409, {"message": "stock posting is using these definitions; retry after it completes"}
    )
    assert temporary.definite is False
    assert OwnerRejectedError(409, {"message": "product configuration changed"}).definite is True


def test_opening_serial_count_and_skip_shape_are_exact():
    with pytest.raises(ValidationError, match="serial count"):
        AdvancedOpeningInput.model_validate(
            {
                "decision": "OPEN",
                "opening_date": "2026-04-01",
                "opening_quantity": "2",
                "purchase_price": "12.50",
                "serials": [
                    {"identifiers": [{"identifier_type": "SERIAL", "value": "ONE"}]}
                ],
            }
        )
    with pytest.raises(ValidationError, match="skip opening"):
        AdvancedOpeningInput.model_validate(
            {"decision": "SKIP", "opening_quantity": "1"}
        )


async def active_definition(client, factory, tenant):
    _, auth, base, body, created = await definition(client, factory, tenant)
    creation_id = uuid.UUID(created["creation"]["id"])
    item_id = uuid.UUID(created["skus"][0]["id"])
    with tenant_scope(tenant):
        async with factory.begin() as db:
            receipt = await db.get(AdvancedProductCreation, creation_id)
            item = await db.get(Item, item_id)
            family = await db.get(ProductFamily, uuid.UUID(created["family"]["id"]))
            assert receipt is not None and item is not None and family is not None
            user_id = receipt.owner_user_id
            item.status, family.status = "ACTIVE", "ACTIVE"
            entry = dict(receipt.progress.get("skus", {}).get(str(item_id), {}))
            entry.update(setup_done=True, prices_published=True, activated=True)
            progress = dict(receipt.progress)
            progress["skus"] = {**progress.get("skus", {}), str(item_id): entry}
            receipt.progress, receipt.status, receipt.step = progress, "OPENING", "OPENING"
    signed = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant,
        company_id=uuid.UUID(created["creation"]["company_id"]),
        user_id=user_id,
        base_currency="INR",
        features=frozenset({"inventory"}),
        finance=FinancialContext(
            configuration_hash="a" * 64,
            company_active=True,
            books_begin_date=dt.date(2026, 4, 1),
            fiscal_year_start_month=4,
            fiscal_year_start_day=1,
            amount_precision=2,
            rounding_mode="half_up",
            default_payment_terms_days=0,
            timezone="Asia/Kolkata",
        ),
    )
    token, signature = sign_company_context(signed, ACTOR_SECRET.encode())
    auth |= {"x-company-context": token, "x-company-signature": signature}
    path = base + "/definitions/" + str(creation_id) + "/skus/" + str(item_id)
    return auth, base, body, created, path


async def test_options_show_verified_books_begin_date(client, factory, tenant_a):
    auth, base, _, _, _ = await active_definition(client, factory, tenant_a)
    response = await client.get(base + "/options", headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["books_begin_date"] == "2026-04-01"


async def test_skip_opening_completes_and_replays(client, factory, tenant_a):
    auth, _, _, created, path = await active_definition(client, factory, tenant_a)
    payload = {
        "expected_creation_version": created["creation"]["row_version"],
        "opening": {"decision": "SKIP"},
    }
    key = str(uuid7())
    signed = {**auth, "Idempotency-Key": key}
    response = await client.post(path + "/opening", headers=signed, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETE"
    assert response.json()["sku_progress"][0]["opening_state"] == "SKIPPED"
    replay = await client.post(path + "/opening", headers=signed, json=payload)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"


async def test_native_preflight_requires_books_begin_base_unit(client, factory, tenant_a):
    auth, _, _, _, path = await active_definition(client, factory, tenant_a)
    result = await client.post(
        path + "/opening-preflight",
        headers=auth,
        json={
            "decision": "OPEN",
            "opening_date": "2026-04-01",
            "opening_quantity": "3",
            "purchase_price": "12.50",
        },
    )
    assert result.status_code == 409, result.text
    assert "base unit" in result.json()["error"]["message"].lower()


@pytest.mark.parametrize("source_delivery", [False, True])
async def test_opening_retries_uncertain_owner_with_same_command(
    client, factory, tenant_a, monkeypatch, app, source_delivery
):
    if source_delivery:
        from pydantic import SecretStr

        from catalog.config import VoucherSourceDelivery

        app.state.settings = app.state.settings.model_copy(update={
            "voucher_source_delivery": VoucherSourceDelivery(
                key_id="catalog.advanced.test",
                secret=SecretStr("test-only-source-key-" + "x" * 32),
            ),
        })
    auth, base, body, created, path = await active_definition(client, factory, tenant_a)
    unit_id = body["skus"][0]["item"]["base_unit_id"]
    warehouse_id, type_id, revision_id, control_id, voucher_id = [str(uuid7()) for _ in range(5)]
    state = {"closed": True, "lost": False, "status": "DRAFT", "control_keys": []}

    async def source_bundle(self, source_tenant, source_company, source_item, creation):
        assert source_tenant == tenant_a
        assert str(source_company) == created["creation"]["company_id"]
        assert str(source_item) == created["skus"][0]["id"]
        return {"message_id": str(creation), "masters": []}

    async def deliver(self, bundle):
        state["source"] = bundle
        return {"applied": True}

    if source_delivery:
        monkeypatch.setattr(CreationOwners, "item_source_bundle", source_bundle)
        monkeypatch.setattr(CreationOwners, "deliver_source", deliver)

    async def local(db, actor, context, creation_id, item_id, opening):
        request = SimpleCreationInput(
            kind="GOODS",
            name="Product SKU",
            base_unit_id=uuid.UUID(unit_id),
            opening_date=opening.opening_date,
            opening_quantity=opening.opening_quantity,
            purchase_price=opening.purchase_price,
            batch_enabled=False,
        )
        return request, [], Decimal("3"), set()

    async def owner(self, service, method, target, payload=None, key=None):
        if target.endswith("/stock/openings/capture-fields"):
            return {"fields": [{"key": "quantity", "readable": True, "writable": True}]}
        if target.endswith("/stock/openings/readiness"):
            return {"blockers": ["BOOKS_CLOSED"] if state["closed"] else []}
        if target.endswith("/voucher-capabilities"):
            return {"stock_execution": True}
        if "/voucher-types?" in target:
            return {"items": [{"id": type_id, "profile": "OPENING"}]}
        if "/effective-configuration?" in target:
            return {"policy": {"approval_required": False}}
        if "/voucher-types/" in target:
            return {"revision_id": revision_id}
        if target.endswith("/warehouse-configuration"):
            return {"default_opening_warehouse_id": None, "main_warehouse_id": None}
        if target.endswith("/warehouses/" + warehouse_id):
            return {"id": warehouse_id, "is_active": True}
        if "effective-facts?" in target:
            return {
                "units": [{"usage_role": "BASE", "revision_id": str(uuid7())}],
                "item_version": 2,
            }
        if target.endswith("/stock/openings/calculate"):
            assert Decimal(payload["opening"]["unit_cost"]) == Decimal("12.50")
            return {"base_quantity": "3", "received_value": "37.50"}
        if "/stock/openings/products/" in target:
            state["control_keys"].append(key)
            assert payload["lines"][0]["received_value"] == "37.50"
            if not state["lost"]:
                state["lost"] = True
                raise ServiceUnavailableError("Simulated response loss after owner commit")
            return {"id": control_id}
        if target.endswith("/vouchers") and method == "POST":
            if source_delivery:
                assert state.get("source") is not None
            assert payload["stock"]["opening_control_id"] == control_id
            return {"id": voucher_id}
        if target.endswith("/submit"):
            state["status"] = "APPROVED"
            return {"status": "APPROVED"}
        if target.endswith("/issue"):
            state["status"] = "ISSUED"
            return {"status": "ISSUED"}
        if target.endswith("/post"):
            state["status"] = "POSTED"
            return {"operation_id": str(uuid7())}
        if target.endswith("/reconciliation"):
            return {"blockers": [], "expected_version": 1, "manifest_hash": "a" * 64}
        if target.endswith("/finalize"):
            return {"status": "FINALIZED"}
        if target.endswith("/vouchers/" + voucher_id):
            return {"row_version": 1, "status": state["status"]}
        raise AssertionError((service, method, target))

    monkeypatch.setattr(opening_tasks, "local_preflight", local)
    monkeypatch.setattr(CreationOwners, "call", owner)
    payload = {
        "expected_creation_version": created["creation"]["row_version"],
        "opening": {
            "decision": "OPEN",
            "opening_date": "2026-04-01",
            "warehouse_id": warehouse_id,
            "opening_quantity": "3",
            "purchase_price": "12.50",
        },
    }
    rejected = await client.post(
        path + "/opening", headers={**auth, "Idempotency-Key": str(uuid7())}, json=payload
    )
    assert rejected.status_code == 409, rejected.text
    status = await client.get(base + "/definitions/" + created["creation"]["id"], headers=auth)
    assert status.status_code == 200
    assert status.json()["sku_progress"][0]["opening_state"] == "NOT_REQUESTED"
    state["closed"] = False
    accepted = await client.post(
        path + "/opening", headers={**auth, "Idempotency-Key": str(uuid7())}, json=payload
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["sku_progress"][0]["opening_step"] == "OPENING"
    lost = await client.post(path + "/opening/advance", headers=auth)
    assert lost.status_code == 503, lost.text
    pending = await client.get(base + "/definitions/" + created["creation"]["id"], headers=auth)
    assert pending.json()["sku_progress"][0]["opening_state"] == "IN_PROGRESS"
    for _ in range(8):
        continued = await client.post(path + "/opening/advance", headers=auth)
        assert continued.status_code == 200, continued.text
        if continued.json()["sku_progress"][0]["opening_state"] == "POSTED":
            break
    assert continued.json()["status"] == "COMPLETE"
    assert continued.json()["sku_progress"][0]["opening_control_id"] == control_id
    assert state["control_keys"] == [state["control_keys"][0]] * 2
    if source_delivery:
        with tenant_scope(tenant_a):
            async with factory() as db:
                receipt = await db.get(
                    AdvancedProductCreation, uuid.UUID(created["creation"]["id"])
                )
                assert receipt is not None
                assert receipt.progress["skus"][created["skus"][0]["id"]][
                    "opening_progress"
                ]["source_delivered"] is True


async def test_partial_posted_variant_receipt_survives_later_skip(client, factory, tenant_a):
    company, user, _, base, body = await prepared(client, factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    records = await seed_attributes(factory, tenant_a, company)
    definition_id = str(records["attribute_definition"])
    blue = str(records["attribute_option"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            digest, canonical = AttributeValue("TEXT", "Red").canonical()
            red = AttributeOption(
                tenant_id=tenant_a,
                company_id=company,
                definition_id=records["attribute_definition"],
                code="RED",
                name="Red",
                value_type="TEXT",
                value_text="Red",
                value_hash=digest,
                canonical_value=canonical,
            )
            db.add(red)
            await db.flush()
            red_id = str(red.id)
    body["attributes"] = [
        {
            "definition_id": definition_id,
            "is_axis": True,
            "is_required": True,
            "position": 0,
            "options": [blue, red_id],
        }
    ]
    body["skus"][0]["attributes"] = [
        {"definition_id": definition_id, "option_id": blue, "value_type": "TEXT"}
    ]
    body["skus"].append(
        {
            "item": {
                "sku": "RED-SKU",
                "name": "Red product",
                "base_unit_id": body["skus"][0]["item"]["base_unit_id"],
            },
            "attributes": [
                {"definition_id": definition_id, "option_id": red_id, "value_type": "TEXT"}
            ],
        }
    )
    created_response = await client.post(
        base + "/definitions",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    ids = [sku["id"] for sku in created["skus"]]
    control_id = str(uuid7())
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            receipt = await db.get(AdvancedProductCreation, uuid.UUID(created["creation"]["id"]))
            assert receipt is not None
            for value in ids:
                sku = await db.get(Item, uuid.UUID(value))
                assert sku is not None
                sku.status = "ACTIVE"
            family = await db.get(ProductFamily, uuid.UUID(created["family"]["id"]))
            assert family is not None
            family.status = "ACTIVE"
            receipt.progress = {
                "skus": {
                    ids[0]: {
                        "activated": True,
                        "opening_state": "POSTED",
                        "opening_control_id": control_id,
                    },
                    ids[1]: {"activated": True},
                }
            }
            receipt.status, receipt.step = "OPENING", "OPENING"
    signed = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant_a,
        company_id=company,
        user_id=user,
        base_currency="INR",
    )
    token, signature = sign_company_context(signed, ACTOR_SECRET.encode())
    auth |= {"x-company-context": token, "x-company-signature": signature}
    path = base + "/definitions/" + created["creation"]["id"] + "/skus/" + ids[1]
    response = await client.post(
        path + "/opening",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_creation_version": created["creation"]["row_version"],
            "opening": {"decision": "SKIP"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETE"
    assert response.json()["sku_progress"][0]["opening_control_id"] == control_id
    assert response.json()["sku_progress"][1]["opening_state"] == "SKIPPED"
