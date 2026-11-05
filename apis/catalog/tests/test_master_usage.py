import uuid

import httpx
import pytest
from billing_platform.errors import ValidationFailedError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.schemas.master_references import MasterEntity
from catalog.tasks.master_usage import dependencies
from tests.test_api import headers
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_master_references import setup_owner


def test_usage_registry_covers_all_supported_masters_and_native_profile_links() -> None:
    from typing import get_args

    for entity in get_args(MasterEntity):
        relations = dependencies(entity)
        assert len({row.key for row in relations}) == len(relations)
        assert {row.key for row in relations} >= {
            "catalog.master_alias.target_id",
            "catalog.master_external_key.target_id",
        }
    assert "catalog.product_type_revision.handling_revision_id" not in {
        row.key for row in dependencies("catalog.handling_profile")
    }  # Its actual direct usage is the immutable profile revision; type references that revision.
    assert "catalog.handling_profile_revision.profile_id" in {
        row.key for row in dependencies("catalog.handling_profile")
    }


async def test_master_usage_pages_are_protected_scoped_and_not_retirement_certificates(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, _ = await setup_owner(client, factory, tenant_a)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "brand.read",
            "brand.manage",
            "brand_series.read",
            "brand_series.manage",
            "master_alias.read",
            "master_alias.manage",
            "master_external_key.read",
        ],
    )
    brand_id = owner.rsplit("/", 1)[1]
    expected: set[str] = set()
    for code in ("ONE", "TWO", "THREE"):
        row = await create(
            client,
            company,
            current,
            "brand-series",
            {"code": code, "name": code, "brand_id": brand_id},
        )
        assert row.status_code == 201, row.text
        expected.add(row.json()["id"])
    alias = await client.post(
        owner + "/aliases", headers=command_headers(current), json={"alias": "Acme"}
    )
    assert alias.status_code == 201
    relation = "catalog.brand_series.brand_id"
    catalog = await client.get(owner + "/usage-relations", headers=current)
    assert catalog.status_code == 200, catalog.text
    assert relation in {row["key"] for row in catalog.json()["relations"]}
    assert catalog.json()["external_usage"] == "unavailable"
    assert catalog.json()["retirement_check"] == "use_lifecycle_command"
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(3):
        params: dict[str, str | int | bool] = {"relation": relation, "limit": 1, "sort": "-id"}
        if cursor:
            params["cursor"] = cursor
        page = await client.get(owner + "/usage", headers=current, params=params)
        assert page.status_code == 200, page.text
        assert not (seen & {row["id"] for row in page.json()["items"]})
        seen.update(row["id"] for row in page.json()["items"])
        cursor = page.json()["page"]["next_cursor"]
    assert seen == expected and cursor is None
    mapped = await client.get(
        owner + "/usage", headers=current, params={"relation": "catalog.master_alias.target_id"}
    )
    assert mapped.status_code == 200 and mapped.json()["items"][0]["id"] == alias.json()["id"]
    invalid_queries: tuple[dict[str, str | int | bool], ...] = (
        {"relation": "catalog.company.secret"},
        {"relation": relation, "published": True},
        {"relation": relation, "q": "ONE"},
        {"relation": relation, "sort": "name"},
    )
    for invalid in invalid_queries:
        assert (
            await client.get(owner + "/usage", headers=current, params=invalid)
        ).status_code == 422
    assert (await client.get(owner + "/usage-relations")).status_code == 401
    assert (await client.get(owner + "/usage", params={"relation": relation})).status_code == 401
    await policy(factory, tenant_a, company, user, "catalog.brand_series", "brand_id", "read")
    catalog = await client.get(owner + "/usage-relations", headers=current)
    assert relation not in {row["key"] for row in catalog.json()["relations"]}
    assert (
        await client.get(owner + "/usage", headers=current, params={"relation": relation})
    ).status_code == 403


async def test_usage_publication_filters_and_hidden_lifecycle_are_authorized(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from tests.test_handling_api import setup_profile

    company, user, current, master = await setup_profile(client, factory, tenant_a)
    draft = await client.post(master + "/revisions", headers=command_headers(current), json={})
    assert draft.status_code == 201
    target = master.rsplit("/", 1)[1]
    route = f"/v1/companies/{company}/masters/catalog.handling_profile/{target}/usage"
    relation = "catalog.handling_profile_revision.profile_id"
    params = {"relation": relation, "published": "false"}
    pending = await client.get(route, headers=current, params=params)
    assert pending.status_code == 200 and pending.json()["items"][0]["id"] == draft.json()["id"]
    assert (
        await client.get(route, headers=current, params={**params, "published": "true"})
    ).json()["items"] == []
    published = await client.post(
        master + "/revisions/" + draft.json()["id"] + "/publish",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert published.status_code == 200
    assert (
        await client.get(route, headers=current, params={**params, "published": "true"})
    ).json()["items"][0]["id"] == draft.json()["id"]
    catalog = await client.get(route.rsplit("/", 1)[0] + "/usage-relations", headers=current)
    assert {row["key"] for row in catalog.json()["relations"]} == {relation}
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.handling_profile_revision",
        "published_at",
        "read",
    )
    assert (await client.get(route, headers=current, params=params)).status_code == 403
    assert (
        await client.get(route, headers=current, params={"relation": relation})
    ).status_code == 200


async def test_usage_activity_filters_do_not_hide_retained_dependencies(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, _ = await setup_owner(client, factory, tenant_a)
    alias = await client.post(
        owner + "/aliases", headers=command_headers(current), json={"alias": "A"}
    )
    assert alias.status_code == 201
    relation = "catalog.master_alias.target_id"
    params = {"relation": relation, "is_active": "true"}
    assert (await client.get(owner + "/usage", headers=current, params=params)).json()["items"][0][
        "id"
    ] == alias.json()["id"]
    assert (
        await client.post(
            owner + "/aliases/" + alias.json()["id"] + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (await client.get(owner + "/usage", headers=current, params=params)).json()[
        "items"
    ] == []
    assert (
        len(
            (
                await client.get(
                    owner + "/usage",
                    headers=current,
                    params={"relation": relation, "is_active": "false"},
                )
            ).json()["items"]
        )
        == 1
    )
    await policy(factory, tenant_a, company, user, "catalog.master_alias", "is_active", "read")
    assert (await client.get(owner + "/usage", headers=current, params=params)).status_code == 403
    assert (
        len(
            (
                await client.get(owner + "/usage", headers=current, params={"relation": relation})
            ).json()["items"]
        )
        == 1
    )


def test_usage_registry_rejects_external_targets() -> None:
    with pytest.raises(ValidationFailedError):
        dependencies("billing.party")
