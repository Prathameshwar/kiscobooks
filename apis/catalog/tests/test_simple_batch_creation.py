"""Native Catalog batch prices and resumable multi-cohort creation contracts."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select, update

from catalog.models.commercial import ProductTypeRevision
from catalog.models.configuration import ProductPricingPolicy
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.pricing import ItemPrice, ItemPriceScope, PricePlan
from catalog.models.product_stock_choice import ItemStockChoice
from catalog.models.projections import CompanyFeatureProjection
from catalog.tasks.simple_creation_transport import CreationOwners, ServiceUnavailableError
from tests.conftest import ACTOR_SECRET
from tests.test_simple_product_creation import starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def batch_starter(factory, tenant):
    root, auth, unit = await starter(factory, tenant, inventory=True)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant):
        async with factory.begin() as db:
            for feature in ("batch_tracking", "expiry_tracking"):
                db.add(
                    CompanyFeatureProjection(
                        id=uuid7(),
                        tenant_id=tenant,
                        company_id=company,
                        source_id=uuid7(),
                        source_version=2,
                        source_company_id=company,
                        feature_key=feature,
                        is_enabled=True,
                        locked_at=None,
                    )
                )
            await db.execute(
                update(ProductTypeRevision)
                .where(ProductTypeRevision.kind == "GOODS")
                .values(tracking_modes=["NONE", "BATCH"])
            )
            await db.execute(update(InventoryProfileTemplateRevision).values(lot_tracking=True))
            await db.execute(update(ProductPricingPolicy).values(mrp_mode="OPTIONAL"))
            await db.execute(
                update(PricePlan).where(PricePlan.purpose == "SALE").values(tax_basis="INCLUSIVE")
            )
    context = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    context = context.model_copy(
        update={"features": frozenset({"inventory", "batch_tracking", "expiry_tracking"})}
    )
    token, signature = sign_company_context(context, ACTOR_SECRET.encode())
    return root, auth | {"x-company-context": token, "x-company-signature": signature}, unit


async def test_two_batches_have_distinct_native_prices_and_retry_receipts(
    client, factory, tenant_a, monkeypatch
):
    root, auth, unit = await batch_starter(factory, tenant_a)
    original = CreationOwners.call
    retained = {}
    lost = False

    async def owner(self, service, method, path, body=None, key=None):
        nonlocal lost
        if service == "catalog":
            return await original(self, service, method, path, body, key)
        if path.endswith("/capture-fields"):
            return {
                "fields": [{"key": "quantity", "visible": True, "readable": True, "writable": True}]
            }
        if path.endswith("/field-set?action=prepare"):
            return {
                "fields": [
                    {"key": value, "readable": True, "visible": True, "writable": True}
                    for value in (
                        "item_id",
                        "code",
                        "reason",
                        "manufactured_on",
                        "expires_on",
                        "mrp_amount",
                        "mrp_currency",
                        "mrp_unit_id",
                    )
                ]
            }
        if path.endswith("/batches") and method == "POST":
            if key not in retained:
                retained[key] = {
                    "id": str(uuid7()),
                    "company_id": root.rsplit("/", 1)[1],
                    "item_id": body["item_id"],
                    "status": "ACTIVE",
                    "is_held": False,
                    "mrp_amount": body["mrp_amount"],
                    "mrp_currency": body["mrp_currency"],
                    "mrp_unit_id": body["mrp_unit_id"],
                }
            if not lost:
                lost = True
                raise ServiceUnavailableError("Lost response after owner commit")
            return retained[key]
        if "/batches/" in path:
            return next(value for value in retained.values() if path.endswith(value["id"]))
        raise AssertionError(path)

    monkeypatch.setattr(CreationOwners, "call", owner)
    options = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert options.status_code == 200, options.text
    assert options.json()["batch"] == {
        "available": True,
        "required": False,
        "expiry_enabled": True,
        "expiry_required": False,
        "manufacture_date_required": False,
    }
    assert {"batch_enabled", "batch_code", "batch_expires_on"} <= {
        value["key"] for value in options.json()["fields"]
    }
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "name": "Two batches",
            "base_unit_id": unit,
            "batch_enabled": True,
            "batches": [
                {"code": "A", "purchase_price": "10", "sale_price": "20", "mrp": "30"},
                {"code": "B", "purchase_price": "15", "sale_price": "25", "mrp": "35"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    identity = response.json()["id"]
    for _ in range(20):
        result = await client.post(
            root + f"/simple-product-creations/{identity}/advance", headers=auth
        )
        if result.status_code == 503:
            continue
        assert result.status_code == 200, result.text
        if result.json()["status"] == "COMPLETE":
            break
    assert result.json()["status"] == "COMPLETE"
    assert len(retained) == 2
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.scalar(select(ItemStockChoice))).batch_enabled
            scopes = list(await db.scalars(select(ItemPriceScope)))
            assert len(scopes) == 2 and {scope.subject_kind for scope in scopes} == {"LOT"}
            assert {scope.lot_mrp for scope in scopes} == {Decimal("30"), Decimal("35")}
            assert len(list(await db.scalars(select(ItemPrice)))) == 4
    item_id = result.json()["item_id"]
    today = dt.date.today().isoformat()
    response = await client.get(
        root + f"/items/{item_id}/effective-facts?as_of={today}", headers=auth
    )
    assert response.status_code == 200, response.text
    facts = response.json()
    base = next(value for value in facts["units"] if value["usage_role"] == "BASE")
    for value, amount in zip(retained.values(), ("20", "25"), strict=True):
        resolved = await client.post(
            root + "/prices/resolve",
            headers=auth,
            json={
                "item_id": item_id,
                "lot_id": value["id"],
                "unit_revision_id": base["revision_id"],
                "currency": "INR",
                "quantity": "1",
                "as_of": facts["as_of"],
                "purpose": "SALE",
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert Decimal(resolved.json()["amount"]) == Decimal(amount)
    query = {
        "item_id": item_id,
        "unit_revision_id": base["revision_id"],
        "currency": "INR",
        "quantity": "1",
        "as_of": today,
    }
    assert (
        await client.post(root + "/prices/resolve", headers=auth, json=query)
    ).status_code == 422
    foreign = next(iter(retained.values()))
    foreign["company_id"] = str(uuid7())
    assert (
        await client.post(
            root + "/prices/resolve", headers=auth, json=query | {"lot_id": foreign["id"]}
        )
    ).status_code == 403


async def test_optional_batch_off_pins_untracked_profile(client, factory, tenant_a):
    from catalog.models.tax import ItemInventoryProfile
    from tests.test_simple_product_creation import finish

    root, auth, unit = await batch_starter(factory, tenant_a)
    body = {
        "name": "No batch",
        "base_unit_id": unit,
        "batch_enabled": False,
        "purchase_price": "10",
        "sale_price": "20",
    }
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert response.status_code == 201, response.text
    await finish(client, root, auth, response.json()["id"])
    with tenant_scope(tenant_a):
        async with factory() as db:
            profile = await db.scalar(select(ItemInventoryProfile))
            assert not profile.lot_tracking and not profile.expiry_required
            assert profile.issue_strategy == "FIFO"
            assert not (await db.scalar(select(ItemStockChoice))).batch_enabled
