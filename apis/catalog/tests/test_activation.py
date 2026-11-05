import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CatalogDefaultProfile,
    ItemBarcode,
    ProductConfigurationAdoption,
    ProductEntryOptionPolicy,
    ProductPricingPolicy,
)
from catalog.models.warehouse_policies import ItemWarehousePolicy
from catalog.tasks import activation, product_units
from tests.product_review_factories import changed
from tests.tax_factories import DATE, seed_tax
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_reviewed_activation_freezes_structure_and_replays_once(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    value = preview.json()
    body = {
        key: value[key]
        for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
    }
    request = command_headers(auth)
    activated = await client.post(route + "/activate", headers=request, json=body)
    assert activated.status_code == 200, activated.text
    replay = await client.post(route + "/activate", headers=request, json=body)
    assert (
        replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    detail = await client.get(route, headers=auth)
    assert detail.json()["status"] == "ACTIVE", detail.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            adopted = await db.scalar(
                select(ProductConfigurationAdoption).where(
                    ProductConfigurationAdoption.item_id == ids["item"],
                    ProductConfigurationAdoption.revision == 2,
                )
            )
            assert adopted is not None and adopted.resolution_version == 2
    scanned = await client.post(
        root + "/barcodes/resolve",
        headers=auth,
        json={"scan_value": "000abc", "as_of": str(DATE)},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["item_id"] == str(ids["item"])
    assert scanned.json()["unit_id"] == str(ids["unit_of_measure"])
    assert (
        await client.post(
            root + "/barcodes/resolve",
            json={"scan_value": "000abc", "as_of": str(DATE)},
        )
    ).status_code == 401
    outside_scope = await client.post(
        "/v1/companies/" + str(uuid7()) + "/barcodes/resolve",
        headers=auth,
        json={"scan_value": "000abc", "as_of": str(DATE)},
    )
    assert outside_scope.status_code == 403, outside_scope.text
    structural = await client.post(
        route + "/unit-bindings",
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "code": "AFTER",
            "unit_id": str(ids["unit_of_measure"]),
            "role": "SALE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "valid_from": str(DATE),
        },
    )
    assert structural.status_code == 409, structural.text
    barcode = await client.post(
        route + "/barcodes",
        headers=command_headers(auth),
        json={"expected_version": 2, "value": "ACTIVE-ITEM-001", "symbology": "CODE128"},
    )
    assert barcode.status_code == 200, barcode.text
    codes = await client.get(route + "/barcodes", headers=auth)
    assert codes.status_code == 200, codes.text
    new_code = next(code for code in codes.json()["items"] if code["value"] == "ACTIVE-ITEM-001")
    retired = await client.post(
        route + "/barcode-state",
        headers=command_headers(auth),
        json={
            "expected_version": barcode.json()["item_version"],
            "barcode_id": new_code["id"],
            "is_active": False,
        },
    )
    assert retired.status_code == 200, retired.text
    missing = await client.post(
        root + "/barcodes/resolve",
        headers=auth,
        json={"scan_value": "ACTIVE-ITEM-001", "as_of": str(DATE)},
    )
    assert missing.status_code == 404, missing.text
    generated_headers = command_headers(auth)
    generated = await client.post(
        route + "/barcodes/generate",
        headers=generated_headers,
        json={"expected_version": retired.json()["item_version"]},
    )
    assert generated.status_code == 200, generated.text
    replayed = await client.post(
        route + "/barcodes/generate",
        headers=generated_headers,
        json={"expected_version": retired.json()["item_version"]},
    )
    assert replayed.status_code == 200 and replayed.json() == generated.json(), replayed.text
    generated_code = await client.get(
        route + "/barcodes/" + generated.json()["changed_ids"][-1], headers=auth
    )
    assert generated_code.status_code == 200, generated_code.text
    assert generated_code.json()["value"].startswith("I")
    label = await client.get(
        route + "/barcodes/" + generated.json()["changed_ids"][-1] + "/label.svg",
        headers=auth,
    )
    assert label.status_code == 200 and label.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in label.content
    matched = await client.post(
        root + "/barcodes/resolve",
        headers=auth,
        json={"scan_value": generated_code.json()["value"], "as_of": str(DATE)},
    )
    assert matched.status_code == 200 and matched.json()["item_id"] == str(ids["item"])
    gtin = await client.post(
        route + "/barcodes",
        headers=command_headers(auth),
        json={
            "expected_version": generated.json()["item_version"],
            "value": "036000291452",
            "symbology": "GTIN",
        },
    )
    assert gtin.status_code == 200, gtin.text
    duplicate = await client.post(
        route + "/barcodes",
        headers=command_headers(auth),
        json={
            "expected_version": gtin.json()["item_version"],
            "value": "00036000291452",
            "symbology": "GTIN",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    mixed_type_duplicate = await client.post(
        route + "/barcodes",
        headers=command_headers(auth),
        json={
            "expected_version": gtin.json()["item_version"],
            "value": "00036000291452",
            "symbology": "CODE128",
        },
    )
    assert mixed_type_duplicate.status_code == 409, mixed_type_duplicate.text
    gs1 = await client.post(
        root + "/barcodes/resolve",
        headers=auth,
        json={
            "scan_value": "]C101000360002914521725123110LOT7\x1d21SER123",
            "as_of": str(DATE),
        },
    )
    assert gs1.status_code == 200, gs1.text
    assert (gs1.json()["lot_hint"], gs1.json()["serial_hint"]) == ("LOT7", "SER123")
    await policy(
        factory,
        tenant_a,
        uuid.UUID(root.rsplit("/", 1)[1]),
        ids["actor_user"],
        "catalog.item_barcode",
        "value",
        "read",
    )
    denied = await client.post(
        root + "/barcodes/resolve",
        headers=auth,
        json={"scan_value": "036000291452", "as_of": str(DATE)},
    )
    assert denied.status_code == 403, denied.text
    denied_label = await client.get(
        route + "/barcodes/" + generated.json()["changed_ids"][-1] + "/label.svg",
        headers=auth,
    )
    assert denied_label.status_code == 403, denied_label.text
    history = await client.get(
        root + "/item-activations", headers=auth, params={"item_id": str(ids["item"])}
    )
    assert history.status_code == 200 and len(history.json()["items"]) == 1, history.text
    sources = await client.get(root + "/item-activation-sources", headers=auth)
    assert sources.status_code == 200 and sources.json()["items"], sources.text
    again = await client.post(route + "/activate", headers=command_headers(auth), json=body)
    assert again.status_code == 409, again.text


async def test_required_barcode_cannot_be_retired_from_active_item(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            options = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.company_id == company,
                    ProductEntryOptionPolicy.revision_id.is_not(None),
                )
            )
            assert options is not None
            options.barcode_mode = "REQUIRED"
            code = await db.scalar(select(ItemBarcode).where(ItemBarcode.item_id == ids["item"]))
            assert code is not None
            code_id = code.id
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    monkeypatch.setattr(product_units, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    activated = await client.post(
        route + "/activate",
        headers=command_headers(auth),
        json={
            key: preview.json()[key]
            for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
        },
    )
    assert activated.status_code == 200, activated.text
    retired = await client.post(
        route + "/barcode-state",
        headers=command_headers(auth),
        json={"expected_version": 2, "barcode_id": str(code_id), "is_active": False},
    )
    assert retired.status_code == 409, retired.text


async def test_activation_checks_business_date_and_required_purchase_coverage(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"]) + "/activation-preview"
    future = await client.post(route, headers=auth, json={"as_of": "2090-01-02"})
    assert future.status_code == 409, future.text
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        purchase_reference_mode="REQUIRED",
    ):
        preview = await client.post(route, headers=auth, json={"as_of": str(DATE)})
        assert (
            preview.status_code == 200 and "purchase_pricing_policy" in preview.json()["missing"]
        ), preview.text


async def test_non_stock_activation_refuses_staged_location_policy(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    company = uuid.UUID(root.rsplit("/", 1)[-1])
    policy_id = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                ItemWarehousePolicy(
                    id=policy_id,
                    tenant_id=tenant_a,
                    company_id=company,
                    item_id=ids["item"],
                    selection_mode="ALLOW_LIST",
                )
            )
    async with changed(
        factory,
        tenant_a,
        CatalogDefaultProfile,
        ids["catalog_default_profile"],
        inventory_template_revision_mode="CLEAR",
        inventory_template_revision_id=None,
    ):
        response = await client.post(
            root + "/items/" + str(ids["item"]) + "/activation-preview",
            headers=auth,
            json={"as_of": str(DATE)},
        )
        async with changed(
            factory,
            tenant_a,
            ItemWarehousePolicy,
            policy_id,
            selection_mode="ALLOW_ALL_ACTIVE",
        ):
            cleared = await client.post(
                root + "/items/" + str(ids["item"]) + "/activation-preview",
                headers=auth,
                json={"as_of": str(DATE)},
            )
    assert response.status_code == 200, response.text
    assert "inventory_profile_for_location_policy" in response.json()["missing"]
    assert response.json()["eligible"] is False
    assert cleared.status_code == 200, cleared.text
    assert "inventory_profile_for_location_policy" not in cleared.json()["missing"]
