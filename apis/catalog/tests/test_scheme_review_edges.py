import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CategoryScheme, FamilyCategory, Outbox
from tests.tax_factories import seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_scheme_governance import active_product, clock, commit_scheme, setup_scheme

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_category_preview_checks_scope_schema_and_changed_field_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    _, _, other_ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    route = root + "/product-families/" + str(ids["product_family"]) + "/category-preview"
    body = {
        "expected_version": 1,
        "categories": [
            {"scheme_id": str(ids["category_scheme"]), "category_id": str(ids["item_category"])}
        ],
    }
    assert (await client.post(route, json=body)).status_code == 401
    assert (await client.post(route, headers=auth, json={"categories": []})).status_code == 422
    limited = headers(company, tenant=tenant_a, user=ids["actor_user"], permission=["item.read"])
    assert (await client.post(route, headers=limited, json=body)).status_code == 403
    foreign = route.replace(str(ids["product_family"]), str(other_ids["product_family"]))
    assert (await client.post(foreign, headers=auth, json=body)).status_code == 403
    success = await client.post(route, headers=auth, json=body)
    assert success.status_code == 200, success.text
    await policy(
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        "catalog.family_category",
        "category_id",
        "write",
    )
    protected = await client.post(route, headers=auth, json=body)
    assert protected.status_code == 403, protected.text


async def test_scheme_commit_requires_scope_and_untampered_review(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, scheme = await setup_scheme(client, factory, tenant_a)
    _, _, _, foreign = await setup_scheme(client, factory, tenant_a)
    route = f"/v1/companies/{company}/category-schemes/{scheme['id']}"
    body = {
        "expected_version": 1,
        "membership_mode": "MULTIPLE",
        "is_active": True,
        "is_required": False,
    }
    preview = await client.post(route + "/transition-preview", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    commit = {**body, "preview_token": preview.json()["preview_token"]}
    request = command_headers(auth)
    assert (
        await client.post(
            route + "/transition",
            headers={"Idempotency-Key": request["Idempotency-Key"]},
            json=commit,
        )
    ).status_code == 401
    limited = headers(company, tenant=tenant_a, user=user, permission=["category_scheme.read"])
    assert (
        await client.post(route + "/transition", headers=command_headers(limited), json=commit)
    ).status_code == 403
    assert (
        await client.post(
            route.replace(scheme["id"], foreign["id"]) + "/transition", headers=request, json=commit
        )
    ).status_code == 403
    invalid = await client.post(
        route + "/transition", headers=request, json={**body, "preview_token": "invalid"}
    )
    assert invalid.status_code == 422, invalid.text
    stale = await client.post(
        route + "/transition", headers=request, json={**commit, "is_required": True}
    )
    assert stale.status_code == 409, stale.text


async def test_closed_memberships_do_not_prevent_category_and_scheme_retirement(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            value = await db.get(FamilyCategory, ids["family_category"])
            assert value is not None
            value.valid_to = dt.date(2020, 1, 1)
    result = await client.post(
        root + "/item-categories/" + str(ids["item_category"]) + "/deactivate",
        headers=command_headers(auth),
        json={"expected_version": 1},
    )
    assert result.status_code == 200, result.text
    await commit_scheme(
        client,
        root + "/category-schemes/" + str(ids["category_scheme"]),
        auth,
        {
            "expected_version": 1,
            "membership_mode": "SINGLE",
            "is_required": False,
            "is_active": False,
        },
    )
    history = await client.get(
        root + "/product-families/" + str(ids["product_family"]) + "/categories", headers=auth
    )
    assert history.status_code == 200 and len(history.json()["items"]) == 1, history.text


async def test_activation_checks_future_required_category_gap(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            scheme = await db.get(CategoryScheme, ids["category_scheme"])
            assert scheme is not None
            scheme.is_required = True
            membership = await db.get(FamilyCategory, ids["family_category"])
            assert membership is not None
            membership.valid_to = dt.date(2090, 2, 1)
    response = await client.post(
        root + "/items/" + str(ids["item"]) + "/activation-preview",
        headers=auth,
        json={"as_of": "2090-01-01"},
    )
    assert response.status_code == 200 and not response.json()["eligible"], response.text
    assert (
        "scheduled_category_scheme:" + str(ids["category_scheme"]) + ":2090-02-02"
        in response.json()["missing"]
    )


async def test_transition_current_authority_wrong_company_and_atomic_rollback(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, scheme = await setup_scheme(client, factory, tenant_a)
    other_company, _, _, other_scheme = await setup_scheme(client, factory, tenant_a)
    assert company != other_company
    route = f"/v1/companies/{company}/category-schemes/{scheme['id']}"
    body = {
        "expected_version": 1,
        "membership_mode": "MULTIPLE",
        "is_active": True,
        "is_required": False,
    }
    assert (await client.post(route + "/transition-preview", json=body)).status_code == 401
    limited = headers(company, tenant=tenant_a, user=user, permission=["category_scheme.manage"])
    assert (
        await client.post(route + "/transition-preview", headers=limited, json=body)
    ).status_code == 403
    wrong = await client.post(
        f"/v1/companies/{company}/category-schemes/{other_scheme['id']}/transition-preview",
        headers=auth,
        json=body,
    )
    assert wrong.status_code == 403, wrong.text
    before = await client.get(route, headers=auth)
    with tenant_scope(tenant_a):
        async with factory() as db:
            audit_count = await db.scalar(select(func.count(Outbox.id)))
    preview = await client.post(route + "/transition-preview", headers=auth, json=body)
    assert preview.status_code == 200
    await policy(
        factory, tenant_a, company, user, "catalog.category_scheme", "membership_mode", "write"
    )
    rejected = await client.post(
        route + "/transition",
        headers=command_headers(auth),
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert rejected.status_code == 403, rejected.text
    current = await client.get(route, headers=auth)
    assert current.json()["row_version"] == before.json()["row_version"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == audit_count


async def test_transition_replay_rechecks_removed_product_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, scheme = await setup_scheme(client, factory, tenant_a)
    route = f"/v1/companies/{company}/category-schemes/{scheme['id']}"
    body = {
        "expected_version": 1,
        "membership_mode": "SINGLE",
        "is_active": True,
        "is_required": True,
    }
    preview = await client.post(route + "/transition-preview", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    request = command_headers(auth)
    payload = {**body, "preview_token": preview.json()["preview_token"]}
    result = await client.post(route + "/transition", headers=request, json=payload)
    assert result.status_code == 200, result.text
    limited = headers(
        company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS - {"item.read"})
    )
    replay = await client.post(route + "/transition", headers={**request, **limited}, json=payload)
    assert replay.status_code == 403, replay.text


async def test_activation_replay_rechecks_category_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 200, preview.text
    body = {
        key: preview.json()[key]
        for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
    }
    request = command_headers(auth)
    response = await client.post(route + "/activate", headers=request, json=body)
    assert response.status_code == 200, response.text
    limited = headers(
        uuid.UUID(root.rsplit("/", 1)[1]),
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"category_scheme.read"}),
    )
    replay = await client.post(route + "/activate", headers={**request, **limited}, json=body)
    assert replay.status_code == 403, replay.text


async def test_activation_does_not_reauthorize_closed_categories_outside_its_evidence(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, ids = await seed_tax(factory, tenant_a)
    clock(monkeypatch)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            value = await db.get(FamilyCategory, ids["family_category"])
            assert value is not None
            value.valid_to = dt.date(2020, 1, 1)
    auth = headers(
        uuid.UUID(root.rsplit("/", 1)[1]),
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"item_category.read"}),
    )
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    response = await client.post(
        route + "/activate",
        headers=command_headers(auth),
        json={
            key: preview.json()[key]
            for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
        },
    )
    assert response.status_code == 200, response.text


async def test_empty_scheduled_set_cannot_be_retroactively_overlapped(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids, version = await active_product(client, factory, tenant_a, monkeypatch)
    route = root + "/product-families/" + str(ids["product_family"])
    body = {"expected_version": version, "valid_from": "2090-03-01", "categories": []}
    preview = await client.post(route + "/category-preview", headers=auth, json=body)
    assert preview.status_code == 200, preview.text
    response = await client.put(
        route + "/categories",
        headers=command_headers(auth),
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert response.status_code == 200, response.text
    earlier = {
        "expected_version": response.json()["family_version"],
        "valid_from": "2090-02-01",
        "categories": [
            {
                "scheme_id": str(ids["category_scheme"]),
                "category_id": str(ids["item_category"]),
                "is_primary": True,
            }
        ],
    }
    preview = await client.post(route + "/category-preview", headers=auth, json=earlier)
    assert preview.status_code == 409, preview.text
