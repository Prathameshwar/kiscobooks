import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CategoryScheme, FamilyCategory, ItemCategory
from catalog.tasks import activation, category_review, category_schedule, scheme_governance
from tests.tax_factories import seed_tax
from tests.test_api import headers
from tests.test_classification_api import create, setup_source
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (activation, category_review, category_schedule, scheme_governance):
        monkeypatch.setattr(module, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))


async def setup_scheme(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> Any:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant, company, user)
    auth = headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS))
    result = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "AXIS", "name": "Department", "membership_mode": "SINGLE"},
    )
    assert result.status_code == 201, result.text
    return company, user, auth, result.json()


async def commit_scheme(
    client: httpx.AsyncClient, route: str, auth: dict[str, str], body: dict[str, Any]
) -> Any:
    preview = await client.post(route + "/transition-preview", headers=auth, json=body)
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    request = command_headers(auth)
    payload = {**body, "preview_token": preview.json()["preview_token"]}
    result = await client.post(route + "/transition", headers=request, json=payload)
    assert result.status_code == 200, result.text
    replay = await client.post(route + "/transition", headers=request, json=payload)
    assert (
        replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    return result.json()


async def test_reviewed_relaxation_and_retirement_with_inactive_children(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, scheme = await setup_scheme(client, factory, tenant_a)
    child = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "CHILD", "name": "Child", "scheme_id": scheme["id"]},
    )
    assert child.status_code == 201, child.text
    route = f"/v1/companies/{company}/category-schemes/{scheme['id']}"
    updated = await commit_scheme(
        client,
        route,
        auth,
        {
            "expected_version": 1,
            "membership_mode": "MULTIPLE",
            "is_required": False,
            "is_active": True,
        },
    )
    assert updated["membership_mode"] == "MULTIPLE" and updated["row_version"] == 2
    blocked = await client.post(
        route + "/transition-preview",
        headers=auth,
        json={
            "expected_version": 2,
            "membership_mode": "MULTIPLE",
            "is_required": False,
            "is_active": False,
        },
    )
    assert blocked.status_code == 200 and blocked.json()["blockers"] == [
        "active_categories"
    ], blocked.text
    retired = await client.post(
        f"/v1/companies/{company}/item-categories/{child.json()['id']}/deactivate",
        headers=command_headers(auth),
        json={"expected_version": 1},
    )
    assert retired.status_code == 200, retired.text
    retired_scheme = await commit_scheme(
        client,
        route,
        auth,
        {
            "expected_version": 2,
            "membership_mode": "MULTIPLE",
            "is_required": False,
            "is_active": False,
        },
    )
    assert not retired_scheme["is_active"]


async def test_transition_preview_invalidates_after_category_change(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, scheme = await setup_scheme(client, factory, tenant_a)
    route = f"/v1/companies/{company}/category-schemes/{scheme['id']}"
    body = {
        "expected_version": 1,
        "membership_mode": "MULTIPLE",
        "is_required": False,
        "is_active": True,
    }
    preview = await client.post(route + "/transition-preview", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    child = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "NEW", "name": "New", "scheme_id": scheme["id"]},
    )
    assert child.status_code == 201
    result = await client.post(
        route + "/transition",
        headers=command_headers(auth),
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert result.status_code == 409, result.text


async def active_product(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    root, auth, ids = await seed_tax(factory, tenant)
    clock(monkeypatch)
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    source_types = {row["entity_type"] for row in preview.json()["sources"]}
    assert {
        "catalog.family_category",
        "catalog.category_scheme",
        "catalog.item_category",
    } <= source_types
    response = await client.post(
        route + "/activate",
        headers=command_headers(auth),
        json={
            key: preview.json()[key]
            for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
        },
    )
    assert response.status_code == 200, response.text
    return root, auth, ids, response.json()["family_version"]


async def test_active_memberships_are_reviewed_dated_and_preserve_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids, version = await active_product(client, factory, tenant_a, monkeypatch)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    child = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "NEXT", "name": "Next department", "scheme_id": str(ids["category_scheme"])},
    )
    assert child.status_code == 201, child.text
    route = root + "/product-families/" + str(ids["product_family"])
    body = {
        "expected_version": version,
        "valid_from": "2090-02-01",
        "categories": [
            {
                "scheme_id": str(ids["category_scheme"]),
                "category_id": child.json()["id"],
                "is_primary": True,
            }
        ],
    }
    denied = await client.put(route + "/categories", headers=command_headers(auth), json=body)
    assert denied.status_code == 409, denied.text
    preview = await client.post(route + "/category-preview", headers=auth, json=body)
    assert preview.status_code == 200 and preview.json()["closing_count"] == 1, preview.text
    request = command_headers(auth)
    payload = {**body, "preview_token": preview.json()["preview_token"]}
    written = await client.put(route + "/categories", headers=request, json=payload)
    assert written.status_code == 200, written.text
    replay = await client.put(route + "/categories", headers=request, json=payload)
    assert (
        replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    for date, expected in (
        ("2090-01-31", str(ids["item_category"])),
        ("2090-02-01", child.json()["id"]),
    ):
        result = await client.get(route + "/categories", headers=auth, params={"as_of": date})
        assert result.status_code == 200, result.text
        assert [row["category_id"] for row in result.json()["items"]] == [expected]
    history = await client.get(route + "/categories", headers=auth)
    assert len(history.json()["items"]) == 2
    denied_history_auth = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"category_scheme.read"}),
    )
    replay = await client.put(
        route + "/categories", headers={**request, **denied_history_auth}, json=payload
    )
    assert replay.status_code == 403, replay.text


async def test_requiredness_reviews_active_and_future_membership_coverage(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids, version = await active_product(client, factory, tenant_a, monkeypatch)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    required = {
        "expected_version": 1,
        "membership_mode": "SINGLE",
        "is_required": True,
        "is_active": True,
    }
    route = root + "/category-schemes/" + str(ids["category_scheme"])
    result = await commit_scheme(client, route, auth, required)
    assert result["is_required"]
    empty = await client.post(
        root + "/product-families/" + str(ids["product_family"]) + "/category-preview",
        headers=auth,
        json={"expected_version": version, "valid_from": "2090-02-01", "categories": []},
    )
    assert empty.status_code == 409, empty.text
    another = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "OTHER", "name": "Other scheme", "membership_mode": "SINGLE"},
    )
    preview = await client.post(
        root + "/category-schemes/" + another.json()["id"] + "/transition-preview",
        headers=auth,
        json=required,
    )
    assert (
        preview.status_code == 200
        and "active_family_missing_required_scheme" in preview.json()["blockers"]
    ), preview.text


async def test_scheme_transition_checks_each_future_boundary(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            scheme = await db.get(CategoryScheme, ids["category_scheme"])
            assert scheme is not None
            scheme.membership_mode = "MULTIPLE"
            category = ItemCategory(
                tenant_id=tenant_a,
                company_id=company,
                scheme_id=scheme.id,
                code="FUTURE",
                name="Future",
            )
            db.add(category)
            await db.flush()
            db.add(
                FamilyCategory(
                    tenant_id=tenant_a,
                    company_id=company,
                    family_id=ids["product_family"],
                    scheme_id=scheme.id,
                    category_id=category.id,
                    is_primary=False,
                    valid_from=dt.date(2091, 1, 1),
                )
            )
    preview = await client.post(
        root + "/category-schemes/" + str(ids["category_scheme"]) + "/transition-preview",
        headers=auth,
        json={
            "expected_version": 1,
            "membership_mode": "SINGLE",
            "is_required": False,
            "is_active": True,
        },
    )
    assert preview.status_code == 200 and preview.json()["blockers"] == [
        "membership_cardinality"
    ], preview.text


async def test_draft_requirement_reports_each_missing_required_scheme(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            scheme = await db.get(CategoryScheme, ids["category_scheme"])
            assert scheme is not None
            scheme.is_required = True
            membership = await db.get(FamilyCategory, ids["family_category"])
            assert membership is not None
            await db.delete(membership)
    result = await client.get(
        root + "/items/" + str(ids["item"]) + "/requirements",
        headers=auth,
        params={"as_of": "2090-01-01"},
    )
    assert result.status_code == 200, result.text
    assert "category_scheme:" + str(ids["category_scheme"]) in result.json()["missing"]
