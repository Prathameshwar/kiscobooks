import uuid
from typing import Any

import httpx
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers


async def pack_unit(db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID) -> UnitOfMeasure:
    unit = UnitOfMeasure(
        tenant_id=tenant,
        company_id=company,
        code="CASE",
        symbol="case",
        name="Case",
        dimension="COUNT",
        decimal_places=0,
        quantity_increment="1",
    )
    db.add(unit)
    await db.flush()
    return unit


async def setup_pricing(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, *, with_barcode: bool = True
) -> tuple[str, dict[str, str], dict[str, uuid.UUID]]:
    company, ids = await seed_definitions(factory, tenant, with_barcode=with_barcode)
    return (
        f"/v1/companies/{company}",
        headers(
            company, tenant=tenant, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
        ),
        ids,
    )


async def create(
    client: httpx.AsyncClient, root: str, auth: dict[str, str], path: str, body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(root + path, headers=command_headers(auth), json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def guard(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_generation": result["policy_generation"],
        "expected_source_version": result["source_version"],
    }


async def foundation(
    client: httpx.AsyncClient,
    root: str,
    auth: dict[str, str],
    ids: dict[str, uuid.UUID],
    *,
    purpose: str = "SALE",
    tax_basis: str = "EXCLUSIVE",
) -> dict[str, Any]:
    level = await create(client, root, auth, "/pricing/bootstrap", {})
    plan = await create(
        client,
        root,
        auth,
        "/price-plans",
        {
            "code": purpose,
            "name": purpose,
            "purpose": purpose,
            "price_level_id": level["id"] if purpose == "SALE" else None,
            "currency": "INR",
            "tax_basis": tax_basis,
        },
    )
    policy = await create(
        client,
        root,
        auth,
        "/company-pricing-policies",
        {
            **guard(plan),
            "default_level_id": level["id"],
            "purchase_plan_id": plan["id"] if purpose == "PURCHASE" else None,
            "valid_from": "2090-01-01",
        },
    )
    scope = await create(client, root, auth, "/price-scopes", {"item_id": str(ids["item"])})
    numeric = await create(
        client,
        root,
        auth,
        "/price-numeric-revisions",
        {
            **guard(scope),
            "item_id": str(ids["item"]),
            "unit_revision_id": str(ids["item_unit_revision"]),
            "currency": "INR",
            "price_decimal_places": 4,
            "valid_from": "2090-01-01",
        },
    )
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": plan["id"],
            "price_scope_id": scope["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    return {
        "level": level,
        "plan": plan,
        "policy": policy,
        "scope": scope,
        "numeric": numeric,
        "series": series,
    }


async def publish_price(
    client: httpx.AsyncClient, root: str, auth: dict[str, str], setup: dict[str, Any], **values: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    draft = await create(
        client,
        root,
        auth,
        "/price-drafts",
        {
            "series_id": setup["series"]["id"],
            "numeric_revision_id": setup["numeric"]["id"],
            "valid_from": "2090-01-01",
            "price_method": "FIXED",
            "amount": "100",
            "price_basis_quantity": "1",
            **values,
        },
    )
    preview = await client.get(root + "/price-drafts/" + draft["id"] + "/preview", headers=auth)
    assert preview.status_code == 200, preview.text
    token = preview.json()
    published = await create(
        client,
        root,
        auth,
        "/price-drafts/" + draft["id"] + "/publish",
        {**guard(token), "expected_version": token["row_version"]},
    )
    return draft, published
