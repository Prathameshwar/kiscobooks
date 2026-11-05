"""Reference boundaries, revocation and transactional rollback."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CatalogPolicyState, IdempotencyKey, MasterAlias, Outbox
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_master_references import setup_owner


@pytest.mark.parametrize(
    "family,payload",
    [
        ("aliases", {"alias": "Same"}),
        ("external-keys", {"source_namespace": "erp", "external_key": "0001"}),
    ],
)
async def test_foreign_owner_mapping_and_usage_are_scoped(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    family: str,
    payload: dict[str, str],
) -> None:
    first = await setup_owner(client, factory, tenant_a)
    second = await setup_owner(client, factory, tenant_a)
    third = await setup_owner(client, factory, tenant_b)
    _, _, current, owner, prefix = first
    route = owner + "/" + family
    created = await client.post(route, headers=command_headers(current), json=payload)
    assert created.status_code == 201
    for scope, expected in ((second, 403), (third, 404)):
        _, _, other_headers, other_owner, other_prefix = scope
        # Equal keys in another scope are independent claims.
        other = await client.post(
            other_owner + "/" + family, headers=command_headers(other_headers), json=payload
        )
        assert other.status_code == 201
        resolved = await client.get(
            other_prefix + "/" + family + "/resolve", headers=other_headers, params=payload
        )
        assert resolved.json()["id"] == other.json()["id"]
        assert (
            await client.get(route + "/" + other.json()["id"], headers=current)
        ).status_code == expected
        foreign_owner = prefix + "/" + other_owner.rsplit("/", 1)[1]
        assert (
            await client.post(
                foreign_owner + "/" + family, headers=command_headers(current), json=payload
            )
        ).status_code == expected
        for suffix, params in (
            ("usage-relations", {}),
            ("usage", {"relation": "catalog.master_alias.target_id"}),
        ):
            result = await client.get(foreign_owner + "/" + suffix, headers=current, params=params)
            assert result.status_code == expected
        for action in ("activate", "deactivate"):
            response = await client.post(
                route + "/" + other.json()["id"] + "/" + action,
                headers=command_headers(current),
                json={"expected_version": 1},
            )
            assert response.status_code == expected
    page = await client.get(route, headers=current)
    assert [row["id"] for row in page.json()["items"]] == [created.json()["id"]]


async def test_paging_binds_owner_query_and_current_policy(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, _ = await setup_owner(client, factory, tenant_a)
    for alias in ("C", "A", "B"):
        assert (
            await client.post(
                owner + "/aliases", headers=command_headers(current), json={"alias": alias}
            )
        ).status_code == 201
    params: dict[str, str | int] = {"limit": 1}
    first = await client.get(owner + "/aliases", headers=current, params=params)
    assert first.json()["items"][0]["alias"] == "A"
    params["cursor"] = first.json()["page"]["next_cursor"]
    second = await client.get(owner + "/aliases", headers=current, params=params)
    assert second.json()["items"][0]["alias"] == "B"
    tampered = await client.get(
        owner + "/aliases", headers=current, params={**params, "sort": "-id"}
    )
    assert tampered.status_code == 422
    await policy(factory, tenant_a, company, user, "catalog.master_alias", "row_version", "read")
    stale = await client.get(owner + "/aliases", headers=current, params=params)
    assert stale.status_code == 422


async def test_inactive_owner_and_exhausted_versions_leave_no_partial_effects(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    created = await client.post(
        owner + "/aliases", headers=command_headers(current), json={"alias": "A"}
    )
    assert created.status_code == 201
    object_id = uuid.UUID(created.json()["id"])
    detail = owner + "/aliases/" + str(object_id)
    brand = f"/v1/companies/{company}/brands/" + owner.rsplit("/", 1)[1]
    assert (
        await client.post(
            brand + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.get(prefix + "/aliases/resolve", headers=current, params={"alias": "A"})
    ).status_code == 404
    assert (
        await client.post(owner + "/aliases", headers=command_headers(current), json={"alias": "B"})
    ).status_code == 409
    assert (
        await client.post(
            detail + "/activate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    # Historical mappings remain readable on retired masters.
    assert (await client.get(detail, headers=current)).json()["is_active"] is False
    assert (
        await client.post(
            brand + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(MasterAlias, object_id)
            assert row is not None
            row.row_version = 2**31 - 1
        async with factory() as db:
            before = (
                await db.scalar(select(func.count(Outbox.id))),
                await db.scalar(select(func.count(IdempotencyKey.id))),
            )
    exhausted = await client.post(
        detail + "/activate", headers=command_headers(current), json={"expected_version": 2**31 - 1}
    )
    assert exhausted.status_code == 409
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(
                select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
            )
            assert state is not None
            state.generation = 2**63 - 1
    assert (
        await client.post(owner + "/aliases", headers=command_headers(current), json={"alias": "C"})
    ).status_code == 409
    with tenant_scope(tenant_a):
        async with factory() as db:
            after = (
                await db.scalar(select(func.count(Outbox.id))),
                await db.scalar(select(func.count(IdempotencyKey.id))),
            )
            assert before == after
            row = await db.get(MasterAlias, object_id)
            assert row is not None and row.is_active is False
            assert await db.scalar(select(func.count(MasterAlias.id))) == 1


async def test_owner_identity_write_deny_prevents_alias_minting_and_replay(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, _ = await setup_owner(client, factory, tenant_a)
    receipt = command_headers(current)
    body = {"alias": "A"}
    assert (await client.post(owner + "/aliases", headers=receipt, json=body)).status_code == 201
    await policy(factory, tenant_a, company, user, "catalog.brand", "code", "write")
    for auth in (receipt, command_headers(current)):
        assert (await client.post(owner + "/aliases", headers=auth, json=body)).status_code == 403
