"""Simple serial and batch+serial creation through native Catalog commands."""

import uuid
from decimal import Decimal

import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select, update
from voucher_execution.stock import StockInput

from catalog.models.commercial import ProductTypeRevision
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.projections import CompanyFeatureProjection
from catalog.models.tax import ItemInventoryProfile
from catalog.tasks.simple_creation_transport import CreationOwners, ServiceUnavailableError
from tests.conftest import ACTOR_SECRET
from tests.test_simple_batch_creation import batch_starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def serial_starter(factory, tenant, *, batched=False):
    root, auth, unit = await batch_starter(factory, tenant)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant):
        async with factory.begin() as db:
            db.add(
                CompanyFeatureProjection(
                    id=uuid7(),
                    tenant_id=tenant,
                    company_id=company,
                    source_id=uuid7(),
                    source_version=2,
                    source_company_id=company,
                    feature_key="serial_tracking",
                    is_enabled=True,
                    locked_at=None,
                )
            )
            profile = IdentifierProfile(
                id=uuid7(),
                tenant_id=tenant,
                company_id=company,
                code="SERIAL",
                name="Serial",
                is_active=True,
                normalization_version=1,
                row_version=1,
            )
            db.add(profile)
            await db.flush()
            db.add(
                IdentifierProfileRequirement(
                    tenant_id=tenant,
                    company_id=company,
                    profile_id=profile.id,
                    identifier_type="SERIAL",
                    namespace_rule="COMPANY",
                    min_count=1,
                    max_count=1,
                    requires_slot=False,
                )
            )
            await db.execute(
                update(ProductTypeRevision)
                .where(ProductTypeRevision.kind == "GOODS")
                .values(
                    tracking_modes=["BATCH_SERIAL" if batched else "SERIAL"],
                    unit_dimensions=["COUNT"],
                )
            )
            await db.execute(
                update(InventoryProfileTemplateRevision).values(
                    lot_tracking=batched,
                    serial_tracking=True,
                    identifier_profile_id=profile.id,
                )
            )
    context = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    context = context.model_copy(update={"features": context.features | {"serial_tracking"}})
    token, signature = sign_company_context(context, ACTOR_SECRET.encode())
    return root, auth | {"x-company-context": token, "x-company-signature": signature}, unit


@pytest.mark.parametrize("batched", [False, True])
async def test_serials_are_registered_once_and_passed_to_the_opening(
    client, factory, tenant_a, monkeypatch, batched
):
    root, auth, unit = await serial_starter(factory, tenant_a, batched=batched)
    original = CreationOwners.call
    serials, batches, manifests = {}, {}, []
    voucher_id, control_id, type_id, revision_id = (str(uuid7()) for _ in range(4))
    state, lost = "DRAFT", False

    async def owner(self, service, method, path, body=None, key=None):
        nonlocal state, lost
        if service == "catalog":
            return await original(self, service, method, path, body, key)
        if path.endswith("capture-fields"):
            return {
                "fields": [{"key": "quantity", "visible": True, "readable": True, "writable": True}]
            }
        if "field-set?action=prepare" in path:
            return {
                "fields": [
                    {"key": field, "visible": True, "readable": True, "writable": True}
                    for field in (
                        "item_id",
                        "identifiers",
                        "reason",
                        "lot_id",
                        "code",
                        "manufactured_on",
                        "expires_on",
                        "mrp_amount",
                        "mrp_currency",
                        "mrp_unit_id",
                    )
                ]
            }
        if path.endswith("check-identifiers"):
            return {"available": True}
        if path.endswith("/batches") and method == "POST":
            batches.setdefault(
                key,
                {
                    "id": str(uuid7()),
                    "company_id": root.rsplit("/", 1)[1],
                    "item_id": body["item_id"],
                    "status": "ACTIVE",
                    "is_held": False,
                    "mrp_amount": None,
                    "mrp_currency": None,
                    "mrp_unit_id": None,
                },
            )
            return batches[key]
        if "/batches/" in path:
            return next(row for row in batches.values() if path.endswith(row["id"]))
        if path.endswith("/serials") and method == "POST":
            serials.setdefault(key, {"id": str(uuid7()), **body})
            if not lost:
                lost = True
                raise ServiceUnavailableError("Lost serial registration response")
            return serials[key]
        if path.endswith("/stock/openings/readiness"):
            return {"blockers": []}
        if path.endswith("/voucher-capabilities"):
            return {"stock_execution": True}
        if "/voucher-types?" in path:
            return {"items": [{"id": type_id, "profile": "OPENING"}]}
        if "/effective-configuration?" in path:
            return {"policy": {"approval_required": False}}
        if path.endswith("/voucher-types/" + type_id):
            return {"revision_id": revision_id}
        if path.endswith("/stock/openings/calculate"):
            capture = body["opening"]
            return {
                "base_quantity": capture["entered_quantity"],
                "received_value": str(
                    Decimal(capture["entered_quantity"]) * Decimal(capture["unit_cost"])
                ),
            }
        if "/stock/openings/products/" in path:
            manifests.append(body)
            return {"id": control_id}
        if path.endswith("/vouchers"):
            StockInput.model_validate(body["stock"])
            return {"id": voucher_id}
        if path.endswith("/vouchers/" + voucher_id):
            return {"status": state, "row_version": 1}
        for action, status in (("submit", "APPROVED"), ("issue", "ISSUED"), ("post", "POSTED")):
            if path.endswith("/" + action):
                state = status
                return {"operation_id": str(uuid7())}
        if path.endswith("/reconciliation"):
            return {"blockers": [], "expected_version": 1, "manifest_hash": "a" * 64}
        if path.endswith("/finalize"):
            return {"status": "FINALIZED"}
        raise AssertionError(path)

    monkeypatch.setattr(CreationOwners, "call", owner)
    options = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert options.status_code == 200, options.text
    assert options.json()["serial"]["enabled"]
    assert options.json()["batch"]["required"] is batched
    rows = [{"identifiers": [{"identifier_type": "SERIAL", "value": code}]} for code in ("A", "B")]
    stock = {
        "opening_quantity": "2",
        "purchase_price": "12.50",
        "sale_price": "20",
        "serials": rows,
    }
    body = {"name": "Serialized product", "base_unit_id": unit}
    body.update(
        {"batch_enabled": True, "batches": [{"code": "LOT", **stock}]} if batched else stock
    )
    signed = auth | {"Idempotency-Key": str(uuid7())}
    saved = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert saved.status_code == 201, saved.text
    for _ in range(30):
        result = await client.post(
            root + "/simple-product-creations/" + saved.json()["id"] + "/advance", headers=auth
        )
        if result.status_code == 503:
            continue
        assert result.status_code == 200, result.text
        if result.json()["status"] == "COMPLETE":
            break
    assert result.json()["opening_posted"] and result.json()["status"] == "COMPLETE"
    assert len(serials) == 2 and len(manifests) == 1
    line = manifests[0]["lines"][0]
    assert set(line["unit_ids"]) == {row["id"] for row in serials.values()}
    assert Decimal(line["quantity"]) == 2 and Decimal(line["received_value"]) == 25
    assert {row["lot_id"] for row in serials.values()} == {line.get("lot_id")}
    replay = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == saved.json()["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            profile = await db.scalar(select(ItemInventoryProfile))
            assert profile.serial_tracking and profile.lot_tracking is batched


@pytest.mark.parametrize("batched", [False, True])
async def test_serial_product_can_start_without_opening_units(client, factory, tenant_a, batched):
    from tests.test_simple_product_creation import finish

    root, auth, unit = await serial_starter(factory, tenant_a, batched=batched)
    body = {"name": "No opening units", "base_unit_id": unit}
    if batched:
        body["batch_enabled"] = True
    response = await client.post(root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())}, json=body)
    assert response.status_code == 201, response.text
    result = await finish(client, root, auth, response.json()["id"])
    assert result["status"] == "COMPLETE" and not result["opening_posted"]
