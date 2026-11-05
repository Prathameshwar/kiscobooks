import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.pricing import ItemPriceDraft
from tests.pricing_factories import foundation, publish_price, setup_pricing
from tests.pricing_storage_factories import seed_pricing
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_pricing_resolution import query

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_all_pricing_mutations_reject_missing_auth_scope_and_unknown_fields(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    root = f"/v1/companies/{company}"
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    denied = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=["catalog.readiness.read"]
    )
    dated = {"valid_from": "2090-01-01", "expected_generation": 1, "expected_source_version": 1}
    basis = {
        "item_id": str(ids["item"]),
        "unit_revision_id": str(ids["item_unit_revision"]),
        "currency": "INR",
    }
    reference = {
        **dated,
        **basis,
        "numeric_revision_id": str(ids["item_price_numeric_revision"]),
        "amount": "80",
        "price_basis_quantity": "1",
        "source_reference": "Reviewed",
    }
    draft = {
        "series_id": str(ids["item_price_series"]),
        "numeric_revision_id": str(ids["item_price_numeric_revision"]),
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
    }
    cases: list[tuple[str, str, dict[str, Any]]] = [
        ("POST", "/pricing/bootstrap", {}),
        ("POST", "/price-levels", {"code": "LEVEL4", "name": "Level 4", "ordinal": 4}),
        (
            "PATCH",
            "/price-levels/" + str(ids["price_level"]),
            {"name": "Changed", "is_active": True, "expected_version": 1},
        ),
        (
            "POST",
            "/price-plans",
            {
                "code": "NEW",
                "name": "New",
                "purpose": "SALE",
                "price_level_id": str(ids["price_level"]),
                "currency": "INR",
                "tax_basis": "EXCLUSIVE",
            },
        ),
        (
            "PATCH",
            "/price-plans/" + str(ids["price_plan"]),
            {"name": "Updated", "expected_version": 1},
        ),
        (
            "POST",
            "/company-pricing-policies",
            {**dated, "default_level_id": str(ids["price_level"])},
        ),
        ("POST", "/price-scopes", {"item_id": str(ids["item"])}),
        ("POST", "/price-numeric-revisions", {**dated, **basis, "price_decimal_places": 4}),
        (
            "POST",
            "/price-series",
            {
                "plan_id": str(ids["price_plan"]),
                "price_scope_id": str(ids["item_price_scope"]),
                "unit_revision_id": str(ids["item_unit_revision"]),
            },
        ),
        ("POST", "/price-drafts", draft),
        ("PUT", "/price-drafts/" + str(ids["item_price_draft"]), {**draft, "expected_version": 1}),
        (
            "POST",
            "/price-drafts/" + str(ids["item_price_draft"]) + "/publish",
            {"expected_version": 1, "expected_generation": 1, "expected_source_version": 1},
        ),
        ("POST", "/reference-costs", {**reference, "estimate_kind": "STANDARD_ESTIMATE"}),
        ("POST", "/product-mrps", {**reference, "jurisdiction": "IN"}),
        ("POST", "/commercial-guard-rules", {**reference, "rule_kind": "FIXED_MIN"}),
        ("POST", "/commercial-policy-scopes", {"owner_kind": "COMPANY"}),
        (
            "POST",
            "/discount-ceilings",
            {**dated, "scope_id": str(ids["commercial_policy_scope"]), "max_discount_pct": "10"},
        ),
        (
            "POST",
            "/item-commercial-policies",
            {**dated, "item_id": str(ids["item"]), "free_sale_allowed": True},
        ),
    ]
    for method, path, body in cases:
        for supplied, expected in (({}, 401), (denied, 403), (auth, 422)):
            response = await client.request(
                method,
                root + path,
                headers=command_headers(supplied),
                json={**body, **({"unknown": "value"} if expected == 422 else {})},
            )
            assert response.status_code == expected, (path, response.text)
        foreign_company = await client.request(
            method,
            f"/v1/companies/{uuid.uuid4()}" + path,
            headers=command_headers(auth),
            json=body,
        )
        assert foreign_company.status_code == 403, (path, foreign_company.text)
    for path in ("/prices/resolve", "/prices/coverage"):
        for supplied, expected in (({}, 401), (denied, 403)):
            response = await client.post(root + path, headers=supplied, json=query(ids))
            assert response.status_code == expected, response.text
    preview = root + "/price-drafts/" + str(ids["item_price_draft"]) + "/preview"
    for supplied, expected in (({}, 401), (denied, 403)):
        response = await client.get(preview, headers=supplied)
        assert response.status_code == expected, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPriceDraft.id))) == 3


async def test_sale_read_does_not_enumerate_purchase_or_estimate_prices(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    root = f"/v1/companies/{company}"
    sale_permissions = sorted(
        CATALOG_PERMISSIONS
        - {
            "purchase_price.read",
            "purchase_price.manage",
            "reference_cost.read",
            "reference_cost.manage",
            "price_plan.override",
        }
    )
    auth = headers(company, tenant=tenant_a, user=ids["actor_user"], permission=sale_permissions)
    plans = await client.get(root + "/price-plans", headers=auth)
    assert plans.status_code == 200, plans.text
    assert [p["purpose"] for p in plans.json()["items"]] == ["SALE"]
    assert (await client.get(root + "/reference-costs", headers=auth)).status_code == 403
    assert (await client.get(root + "/purchase-price-terms", headers=auth)).status_code == 403
    assert (
        await client.post(
            root + "/prices/resolve", headers=auth, json=query(ids, purpose="PURCHASE")
        )
    ).status_code == 403
    series = await client.get(root + "/price-series", headers=auth)
    assert len(series.json()["items"]) == 1, series.text
    drafts = await client.get(root + "/price-drafts", headers=auth)
    assert len(drafts.json()["items"]) == 2, drafts.text
    # Ordinary sale callers cannot choose another administrative book or level.
    selected = await client.post(
        root + "/prices/resolve",
        headers=auth,
        json=query(ids, price_level_id=str(ids["price_level"]), override_reason="Override"),
    )
    assert selected.status_code == 403, selected.text


async def test_current_field_authority_is_rechecked_on_price_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.test_master_reference_policy import policy

    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    body = {
        "series_id": setup["series"]["id"],
        "numeric_revision_id": setup["numeric"]["id"],
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
    }
    receipt = command_headers(auth)
    initial = await client.post(root + "/price-drafts", headers=receipt, json=body)
    assert initial.status_code == 201, initial.text
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.item_price_draft",
        "amount",
        "write",
        version=3,
    )
    replay = await client.post(root + "/price-drafts", headers=receipt, json=body)
    assert replay.status_code == 403, replay.text


async def test_read_denied_amount_is_omitted_and_cannot_enter_resolution(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.test_master_reference_policy import policy

    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, price = await publish_price(client, root, auth, setup)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.item_price",
        "amount",
        "read",
        version=3,
    )
    detail = await client.get(root + "/prices/" + price["id"], headers=auth)
    assert detail.status_code == 200 and "amount" not in detail.json(), detail.text
    listing = await client.get(root + "/prices", headers=auth)
    assert listing.status_code == 200 and "amount" not in listing.json()["items"][0], listing.text
    assert (
        await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    ).status_code == 403
