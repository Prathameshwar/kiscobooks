import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CatalogPolicyState, IdempotencyKey, Item, Outbox, ProductFamily
from catalog.models import pricing as m
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.pricing_storage_factories import seed_pricing
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_pricing_resolution import query, reference

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def draft_body(ids: dict[str, uuid.UUID], **values: Any) -> dict[str, Any]:
    return {
        "series_id": str(ids["item_price_series"]),
        "numeric_revision_id": str(ids["item_price_numeric_revision"]),
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
        **values,
    }


async def test_draft_dependencies_reject_invalid_sources_without_receipts_or_audit(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    root = f"/v1/companies/{company}"
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            audit_before = await db.scalar(select(func.count(Outbox.id)))
            receipts_before = await db.scalar(select(func.count(IdempotencyKey.id)))
    cases: list[tuple[type[Any], str, dict[str, Any], int]] = [
        (m.PriceLevel, "price_level", {"is_active": False}, 409),
        (Item, "item", {"status": "DISCONTINUED"}, 409),
        (ProductFamily, "product_family", {"status": "DISCONTINUED"}, 409),
        (Item, "item", {"sellable": False}, 409),
        (ItemUnitRevision, "item_unit_revision", {"valid_from": dt.date(2091, 1, 1)}, 409),
        (
            ItemUnitRevision,
            "item_unit_revision",
            {"valid_to": dt.date(2089, 12, 31), "valid_from": dt.date(2089, 1, 1)},
            409,
        ),
        (ItemUnitBinding, "item_unit_binding", {"usage_role": "PURCHASE"}, 409),
        (ItemUnitRevision, "item_unit_revision", {"quantity_decimal_places": 4}, 409),
        (
            m.ItemPriceNumericRevision,
            "item_price_numeric_revision",
            {"valid_from": dt.date(2091, 1, 1)},
            409,
        ),
        (
            m.ItemPriceNumericRevision,
            "item_price_numeric_revision",
            {"valid_from": dt.date(2089, 1, 1), "valid_to": dt.date(2089, 12, 31)},
            409,
        ),
    ]
    for model, key, values, expected in cases:
        async with changed(factory, tenant_a, model, ids[key], **values):
            result = await client.post(
                root + "/price-drafts", headers=command_headers(auth), json=draft_body(ids)
            )
            assert result.status_code == expected, (key, values, result.text)
    invalid_bodies: list[tuple[dict[str, Any], int]] = [
        ({"price_basis_quantity": "0.5"}, 422),
        ({"amount": "0"}, 422),
        (
            {
                "price_method": "FORMULA",
                "amount": None,
                "formula": {
                    "recipe": "REFERENCE_COST_PLUS_MARKUP",
                    "percentage": "10",
                    "estimate_kind": "REPLACEMENT_ESTIMATE",
                    "rounding_mode": "UP",
                },
            },
            409,
        ),
        (
            {
                "price_method": "FORMULA",
                "amount": None,
                "formula": {
                    "recipe": "MRP_LESS_PERCENT",
                    "percentage": "10",
                    "jurisdiction": "IN",
                    "rounding_mode": "UP",
                },
            },
            409,
        ),
        (
            {
                "purchase_term": {
                    "gross_amount": "100",
                    "discount_kind": "NONE",
                    "discount_value": "0",
                }
            },
            422,
        ),
    ]
    for extra, expected in invalid_bodies:
        result = await client.post(
            root + "/price-drafts", headers=command_headers(auth), json=draft_body(ids, **extra)
        )
        assert result.status_code == expected, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == audit_before
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == receipts_before
    async with changed(
        factory,
        tenant_a,
        m.ItemCommercialPolicy,
        ids["item_commercial_policy"],
        free_sale_allowed=True,
    ):
        free = await client.post(
            root + "/price-drafts", headers=command_headers(auth), json=draft_body(ids, amount="0")
        )
        assert free.status_code == 201, free.text


async def test_book_edits_stale_versions_history_and_retirement(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    level_path = root + "/price-levels/" + setup["level"]["id"]
    for body, expected in [
        ({"name": "  ", "is_active": True, "expected_version": 1}, 422),
        ({"name": "x", "is_active": False, "expected_version": 1}, 409),
        ({"name": "x", "is_active": True, "expected_version": 5}, 409),
    ]:
        result = await client.patch(level_path, headers=command_headers(auth), json=body)
        assert result.status_code == expected, result.text
    path = root + "/price-plans/" + setup["plan"]["id"]
    for body, expected in [
        ({"name": "\n", "expected_version": 1}, 422),
        ({"name": "Wholesale", "expected_version": 5}, 409),
        ({"name": "Wholesale", "expected_version": 1, "currency": "USD"}, 422),
    ]:
        assert (
            await client.patch(path, headers=command_headers(auth), json=body)
        ).status_code == expected
    receipt = command_headers(auth)
    body = {"name": " Retail ", "expected_version": 1}
    edited = await client.patch(path, headers=receipt, json=body)
    assert edited.status_code == 200, edited.text
    assert (await client.patch(path, headers=receipt, json=body)).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = await client.get(path, headers=auth)
    assert detail.json()["name"] == "Retail" and detail.json()["currency"] == "INR"
    overlap = {
        **guard(edited.json()),
        "default_level_id": setup["level"]["id"],
        "valid_from": "2090-01-01",
    }
    for extra in (
        {},
        {"expected_source_version": 1},
        {"expected_generation": 1},
        {"supersedes_id": setup["policy"]["id"], "expected_previous_version": 1},
    ):
        response = await client.post(
            root + "/company-pricing-policies",
            headers=command_headers(auth),
            json={**overlap, **extra},
        )
        assert response.status_code == 409, response.text
    future = {
        **overlap,
        "valid_from": "2091-01-01",
        "supersedes_id": setup["policy"]["id"],
        "expected_previous_version": 1,
    }
    successor = await create(client, root, auth, "/company-pricing-policies", future)
    shortened = await client.get(
        root + "/company-pricing-policies/" + setup["policy"]["id"], headers=auth
    )
    assert shortened.json()["valid_to"] == "2090-12-31"
    expired = await client.post(
        root + "/company-pricing-policies",
        headers=command_headers(auth),
        json={**future, **guard(successor), "valid_from": "2092-01-01"},
    )
    assert expired.status_code == 409, expired.text
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory() as db:
            state = await db.scalar(
                select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
            )
            assert state is not None
            state_id = state.id
    async with changed(factory, tenant_a, CatalogPolicyState, state_id, generation=2**63 - 1):
        exhausted = await client.patch(
            path, headers=command_headers(auth), json={"name": "Next", "expected_version": 2}
        )
        assert exhausted.status_code == 409, exhausted.text


async def test_native_books_currency_reference_kinds_and_coverage_contract(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    plan = {
        "code": "OTHER",
        "name": "Other",
        "purpose": "REFERENCE_RETAIL",
        "currency": "INR",
        "tax_basis": "INCLUSIVE",
    }
    for code, expected in (("ZZZ", 422), ("USD", 409)):
        result = await client.post(
            root + "/price-plans", headers=command_headers(auth), json={**plan, "currency": code}
        )
        assert result.status_code == expected, result.text
    for purpose in ("SALE", "PURCHASE"):
        response = await client.post(
            root + "/prices/coverage", headers=auth, json=query(ids, purpose=purpose)
        )
        assert response.status_code == 200 and response.json()["status"] == "MISSING", response.text
    for extra in (
        {"plan_id": setup["plan"]["id"]},
        {"override_reason": "review"},
        {"purpose": "REFERENCE_RETAIL"},
        {
            "purpose": "PURCHASE",
            "price_level_id": setup["level"]["id"],
            "override_reason": "review",
        },
        {"purpose": "PURCHASE", "plan_id": setup["plan"]["id"], "override_reason": "review"},
    ):
        result = await client.post(root + "/prices/resolve", headers=auth, json=query(ids, **extra))
        assert result.status_code == 422, result.text
    retail = await create(client, root, auth, "/price-plans", plan)
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": retail["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    await publish_price(client, root, auth, {**setup, "series": series}, amount="120")
    result = await client.post(
        root + "/prices/resolve",
        headers=auth,
        json=query(ids, purpose="REFERENCE_RETAIL", plan_id=retail["id"]),
    )
    assert result.status_code == 200 and result.json()["amount"] == "120.0000", result.text
    token = await create(client, root, auth, "/pricing/bootstrap", {})
    wrong_kind = await client.post(
        root + "/reference-costs",
        headers=command_headers(auth),
        json=reference(ids, setup, token, estimate_kind="SERVICE_ESTIMATE"),
    )
    assert wrong_kind.status_code == 422, wrong_kind.text


async def test_editing_draft_children_and_published_immutability(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids, purpose="PURCHASE")
    data = {
        "series_id": setup["series"]["id"],
        "numeric_revision_id": setup["numeric"]["id"],
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "72",
        "price_basis_quantity": "1",
        "purchase_term": {"gross_amount": "80", "discount_kind": "PERCENT", "discount_value": "10"},
    }
    wrong = await client.post(
        root + "/price-drafts", headers=command_headers(auth), json={**data, "amount": "73"}
    )
    assert wrong.status_code == 422, wrong.text
    draft = await create(client, root, auth, "/price-drafts", data)
    path = root + "/price-drafts/" + draft["id"]
    edited = await client.put(
        path,
        headers=command_headers(auth),
        json={
            **data,
            "expected_version": 1,
            "amount": "70",
            "purchase_term": {
                "gross_amount": "80",
                "discount_kind": "FIXED_PER_BASIS",
                "discount_value": "10",
            },
        },
    )
    assert edited.status_code == 200, edited.text
    children = await client.get(
        root + "/purchase-price-terms", headers=auth, params={"draft_id": draft["id"]}
    )
    assert (
        len(children.json()["items"]) == 1
        and children.json()["items"][0]["discount_kind"] == "FIXED_PER_BASIS"
    )
    preview = await client.get(path + "/preview", headers=auth)
    token = {**guard(preview.json()), "expected_version": 2}
    stale = await client.post(
        path + "/publish", headers=command_headers(auth), json={**token, "expected_version": 1}
    )
    assert stale.status_code == 409, stale.text
    await create(client, root, auth, "/price-drafts/" + draft["id"] + "/publish", token)
    immutable = await client.put(
        path, headers=command_headers(auth), json={**data, "expected_version": 3}
    )
    assert immutable.status_code == 409, immutable.text
