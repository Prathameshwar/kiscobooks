# Regressions for the confirmed category-scheme review defects.
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
from catalog.tasks import activation
from tests.bulk_factories import post, run
from tests.tax_factories import seed_tax
from tests.test_api import headers
from tests.test_classification_api import create, setup_source
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_category_assignment_preserves_inactive_reference_conflict(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            value = await db.get(ItemCategory, ids["item_category"])
            assert value is not None
            value.is_active = False
    result = await client.put(
        root + "/product-families/" + str(ids["product_family"]) + "/categories",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "categories": [
                {"scheme_id": str(ids["category_scheme"]), "category_id": str(ids["item_category"])}
            ],
        },
    )
    assert result.status_code == 409, result.text


async def scheme(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> Any:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant, company, user)
    response = await create(
        client,
        company,
        auth,
        "category-schemes",
        {
            "code": "AXIS",
            "name": "Review axis",
            "membership_mode": "SINGLE",
        },
    )
    assert response.status_code == 201, response.text
    return company, user, auth, response.json()


async def test_category_authoring_bypasses_scheme_read_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, value = await scheme(client, factory, tenant_a)
    limited = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["item_category.manage", "item_category.read"],
    )
    root = f"/v1/companies/{company}"
    assert (
        await client.get(root + "/category-schemes/" + value["id"], headers=limited)
    ).status_code == 403
    assert (
        await client.get(
            root + "/option-sources/catalog.item_categories",
            headers=limited,
            params={"parent_id": value["id"]},
        )
    ).status_code == 403
    result = await create(
        client,
        company,
        limited,
        "item-categories",
        {
            "code": "BLIND",
            "name": "Blind category",
            "scheme_id": value["id"],
        },
    )
    assert result.status_code == 403, result.text
    await policy(factory, tenant_a, company, user, "catalog.category_scheme", "is_active", "read")
    detail = await client.get(root + "/category-schemes/" + value["id"], headers=auth)
    assert detail.status_code == 200 and "is_active" not in detail.json(), detail.text
    result = await create(
        client,
        company,
        auth,
        "item-categories",
        {
            "code": "HIDDEN_STATUS",
            "name": "Hidden status",
            "scheme_id": value["id"],
        },
    )
    assert result.status_code == 403, result.text


async def test_category_assignment_replay_skips_current_scheme_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    route = root + "/product-families/" + str(ids["product_family"]) + "/categories"
    body = {
        "expected_version": 1,
        "categories": [
            {
                "scheme_id": str(ids["category_scheme"]),
                "category_id": str(ids["item_category"]),
                "is_primary": True,
            }
        ],
    }
    request = command_headers(auth)
    result = await client.put(route, headers=request, json=body)
    assert result.status_code == 200, result.text
    limited = headers(
        uuid.UUID(root.rsplit("/", 1)[1]),
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"category_scheme.read"}),
    )
    fresh = await client.put(
        route, headers=command_headers(limited), json={**body, "expected_version": 2}
    )
    assert fresh.status_code == 403, fresh.text
    replay = await client.put(route, headers={**request, **limited}, json=body)
    assert replay.status_code == 403, replay.text


async def test_activation_accepts_unreadable_category_scheme(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    company = uuid.UUID(root.rsplit("/", 1)[1])
    limited = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"category_scheme.read", "item_category.read"}),
    )
    assert (
        await client.get(root + "/category-schemes/" + str(ids["category_scheme"]), headers=limited)
    ).status_code == 403
    preview = await client.post(
        root + "/items/" + str(ids["item"]) + "/activation-preview",
        headers=limited,
        json={"as_of": "2090-01-01"},
    )
    assert preview.status_code == 403, preview.text


@pytest.mark.parametrize("invalid", ["inactive_scheme", "inactive_category", "single_with_two"])
async def test_activation_does_not_validate_restored_scheme_membership(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            if invalid == "single_with_two":
                cat = ItemCategory(
                    tenant_id=tenant_a,
                    company_id=company,
                    scheme_id=ids["category_scheme"],
                    code="SECOND",
                    name="Second",
                )
                db.add(cat)
                await db.flush()
                db.add(
                    FamilyCategory(
                        tenant_id=tenant_a,
                        company_id=company,
                        family_id=ids["product_family"],
                        scheme_id=ids["category_scheme"],
                        category_id=cat.id,
                        is_primary=False,
                        primary_slot=None,
                    )
                )
            else:
                model, key = (
                    (CategoryScheme, "category_scheme")
                    if invalid == "inactive_scheme"
                    else (ItemCategory, "item_category")
                )
                value = await db.get(model, ids[key])
                assert value is not None
                value.is_active = False
    preview = await client.post(
        root + "/items/" + str(ids["item"]) + "/activation-preview",
        headers=auth,
        json={"as_of": "2090-01-01"},
    )
    assert preview.status_code == 409, preview.text


async def test_bulk_code_matching_silently_chooses_between_two_schemes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, first_scheme = await scheme(client, factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    second_scheme = await create(
        client,
        company,
        auth,
        "category-schemes",
        {
            "code": "SECOND_AXIS",
            "name": "Second axis",
            "membership_mode": "MULTIPLE",
        },
    )
    assert second_scheme.status_code == 201, second_scheme.text
    categories = []
    for parent in (first_scheme, second_scheme.json()):
        child = await create(
            client,
            company,
            auth,
            "item-categories",
            {
                "scheme_id": parent["id"],
                "code": "COMMON",
                "name": "Original " + parent["code"],
            },
        )
        assert child.status_code == 201, child.text
        categories.append(child.json())
    bulk_root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(
        client,
        bulk_root,
        auth,
        "",
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "ambiguous",
                    "change_set": "ambiguous",
                    "resource": "item_category",
                    "action": "UPDATE",
                    "target": {"code": "COMMON"},
                    "data": {"name": "Changed by ambiguous code"},
                }
            ],
        },
    )
    await post(
        client, bulk_root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    await run(factory, tenant_a, company, user, job["id"])
    records = (await client.get(bulk_root + "/" + job["id"] + "/records", headers=auth)).json()[
        "items"
    ]
    assert records[0]["error_code"] == "invalid_record", records
    found = []
    for category in categories:
        result = await client.get(
            f"/v1/companies/{company}/item-categories/" + category["id"], headers=auth
        )
        assert result.status_code == 200, result.text
        found.append(result.json()["name"])
    assert found.count("Changed by ambiguous code") == 0, found
