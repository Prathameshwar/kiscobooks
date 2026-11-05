"""Publication regressions from the Product Tax review; synthetic rates only."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.tax import TaxRateComponent
from tests.pricing_factories import create, guard
from tests.tax_factories import EVIDENCE, components, query, seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("split", [("0", "5"), ("21", "21")])
async def test_invalid_gst_split_is_rejected(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    split: tuple[str, str],
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    entries = components("INTRA_STATE")
    for entry, value in zip(entries, split, strict=True):
        entry["percentage"] = value
    result = await client.post(
        root + "/tax-rates",
        headers=command_headers(auth),
        json={
            **guard(current.json()),
            **EVIDENCE,
            "series_id": str(ids["series_INTRA_STATE"]),
            "valid_from": "2091-01-01",
            "supersedes_id": str(ids["rate_INTRA_STATE"]),
            "expected_previous_version": 1,
            "components": entries,
        },
    )
    assert result.status_code == 422, result.text


async def test_classification_must_cover_entire_binding(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    classification = await create(
        client,
        root,
        auth,
        "/tax-classifications",
        {
            **guard(current.json()),
            **EVIDENCE,
            "valid_from": "2091-01-01",
            "valid_to": "2091-01-01",
            "code_system": "HSN",
            "code": "5678",
            "item_kind": "GOODS",
            "description": "One day",
        },
    )
    result = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={
            **guard(classification),
            "scope_id": str(ids["catalog_tax_scope"]),
            "valid_from": "2091-01-01",
            "supersedes_id": str(ids["binding_SALE_CLASSIFICATION"]),
            "expected_previous_version": 1,
            "direction": "SALE",
            "bundle": "CLASSIFICATION",
            "mode": "OVERRIDE",
            "classification_id": classification["id"],
        },
    )
    assert result.status_code == 409, result.text


async def test_service_rule_cannot_bind_goods_sku(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    rule = await create(
        client,
        root,
        auth,
        "/tax-rules",
        {
            **EVIDENCE,
            "code": "SERVICES",
            "name": "Services only",
            "item_kind": "SERVICE",
            "treatment": "TAXABLE",
            "tax_category_id": str(ids["tax_category"]),
        },
    )
    scope = await create(
        client,
        root,
        auth,
        "/tax-scopes",
        {
            "owner_kind": "SKU",
            "item_id": str(ids["item"]),
        },
    )
    result = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={
            **guard(scope),
            "scope_id": scope["id"],
            "valid_from": "2091-01-01",
            "direction": "SALE",
            "bundle": "RULE",
            "mode": "OVERRIDE",
            "rule_id": rule["id"],
        },
    )
    assert result.status_code == 422, result.text


async def test_scope_replay_rechecks_product_permission(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    body = {"owner_kind": "SKU", "item_id": str(ids["item"])}
    request = command_headers(auth)
    original = await client.post(root + "/tax-scopes", headers=request, json=body)
    assert original.status_code == 201, original.text
    denied = headers(
        uuid.UUID(root.rsplit("/", 1)[1]),
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"item.read"}),
    )
    replay = await client.post(root + "/tax-scopes", headers={**request, **denied}, json=body)
    assert replay.status_code == 403, replay.text


async def test_rate_replay_rechecks_fixed_cess_unit_permission(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    cess = {
        "component_key": "CESS",
        "component": "CESS",
        "kind": "FIXED_PER_UNIT",
        "amount": "2",
        "currency": "INR",
        "unit_id": ids["unit_of_measure"],
        "basis_quantity": "1",
        "rounding_mode": "HALF_UP",
        "position": 2,
    }
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            for context in ("INTRA_STATE", "INTRA_UT", "INTER_STATE"):
                db.add(
                    TaxRateComponent(
                        tenant_id=tenant_a,
                        company_id=company,
                        row_version=1,
                        rate_id=ids["rate_" + context],
                        **cess,
                    )
                )
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert current.status_code == 200, current.text
    body = {
        **guard(current.json()),
        **EVIDENCE,
        "series_id": str(ids["series_INTER_STATE"]),
        "valid_from": "2091-01-01",
        "supersedes_id": str(ids["rate_INTER_STATE"]),
        "expected_previous_version": 1,
        "components": [*components("INTER_STATE"), {**cess, "unit_id": str(cess["unit_id"])}],
    }
    request = command_headers(auth)
    original = await client.post(root + "/tax-rates", headers=request, json=body)
    assert original.status_code == 201, original.text
    denied = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"unit.read"}),
    )
    replay = await client.post(root + "/tax-rates", headers={**request, **denied}, json=body)
    assert replay.status_code == 403, replay.text
