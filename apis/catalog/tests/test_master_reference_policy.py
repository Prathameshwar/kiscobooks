import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, MasterAlias, MasterExternalKey, Outbox
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_master_references import setup_owner


async def policy(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    entity: str,
    field: str,
    access: str,
    version: int = 3,
    condition: dict[str, Any] | None = None,
) -> None:
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": entity,
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": field,
            "access": access,
            "condition": condition,
        },
    )
    await setup_source(factory, tenant, company, user, version=version, facts=(*facts, deny))


@pytest.mark.parametrize(
    "family,entity,field,payload",
    [
        ("aliases", "catalog.master_alias", "alias", {"alias": "Private"}),
        (
            "external-keys",
            "catalog.master_external_key",
            "external_key",
            {"source_namespace": "erp", "external_key": "000Private"},
        ),
    ],
)
async def test_reference_field_denies_precede_lookups_and_protect_retained_receipts(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    family: str,
    entity: str,
    field: str,
    payload: dict[str, str],
) -> None:
    company, user, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    route = owner + "/" + family
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=payload)
    assert created.status_code == 201
    await policy(factory, tenant_a, company, user, entity, field, "write")
    for path, auth in (
        (route, command_headers(current)),
        (route, receipt),
        (prefix + "/" + str(uuid7()) + "/" + family, command_headers(current)),
    ):
        response = await client.post(path, headers=auth, json=payload)
        assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == 2
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 2
    await policy(factory, tenant_a, company, user, entity, field, "read", version=4)
    detail = await client.get(route + "/" + created.json()["id"], headers=current)
    assert detail.status_code == 200 and field not in detail.json()
    if family == "aliases":
        assert "canonical_value" not in detail.json()
    page = await client.get(route, headers=current)
    assert page.status_code == 200 and field not in page.json()["items"][0]
    metadata = await client.get(
        f"/v1/companies/{company}/entities/{entity}/field-set", headers=current
    )
    keys = {row["key"] for row in metadata.json()["fields"]}
    assert field not in keys and (family != "aliases" or "canonical_value" not in keys)
    for query in (payload, {**payload, field: "Absent"}):
        response = await client.get(
            prefix + "/" + family + "/resolve", headers=current, params=query
        )
        assert response.status_code == 403
    query = {"q": "Private"} if family == "aliases" else payload
    assert (await client.get(route, headers=current, params=query)).status_code == 403


async def test_conditional_lifecycle_checks_use_new_version_and_preserve_noop(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, _ = await setup_owner(client, factory, tenant_a)
    created = await client.post(
        owner + "/aliases", headers=command_headers(current), json={"alias": "A"}
    )
    assert created.status_code == 201
    detail = owner + "/aliases/" + created.json()["id"]
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.master_alias",
        "is_active",
        "write",
        condition={"field": "row_version", "cmp": "gt", "value": 1},
    )
    noop = await client.post(
        detail + "/activate", headers=command_headers(current), json={"expected_version": 1}
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 1
    denied = await client.post(
        detail + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
    )
    assert denied.status_code == 403
    stored = (await client.get(detail, headers=current)).json()
    assert stored["is_active"] is True and stored["row_version"] == 1


async def test_owner_denies_cannot_probe_mapping_availability(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    assert (
        await client.post(owner + "/aliases", headers=command_headers(current), json={"alias": "A"})
    ).status_code == 201
    mapping_only = headers(company, tenant=tenant_a, user=user, permission="master_alias.read")
    for label in ("A", "missing"):
        result = await client.get(
            prefix + "/aliases/resolve", headers=mapping_only, params={"alias": label}
        )
        assert result.status_code == 403
    await policy(factory, tenant_a, company, user, "catalog.brand", "code", "read")
    for label in ("A", "missing"):
        assert (
            await client.get(prefix + "/aliases/resolve", headers=current, params={"alias": label})
        ).status_code == 403


@pytest.mark.parametrize(
    "family,model,payload,corrupt",
    [
        ("aliases", MasterAlias, {"alias": "Trusted"}, {"canonical_value": "corrupted"}),
        (
            "external-keys",
            MasterExternalKey,
            {"source_namespace": "erp", "external_key": "0001"},
            {"source_namespace": "INVALID"},
        ),
    ],
)
async def test_corrupt_restored_reference_cannot_be_read_listed_or_replayed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    family: str,
    model: type[MasterAlias] | type[MasterExternalKey],
    payload: dict[str, str],
    corrupt: dict[str, str],
) -> None:
    _, _, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    receipt = command_headers(current)
    route = owner + "/" + family
    created = await client.post(route, headers=receipt, json=payload)
    assert created.status_code == 201
    object_id = uuid.UUID(created.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.get(model, object_id)
            assert row is not None
            for key, value in corrupt.items():
                setattr(row, key, value)
    assert (await client.get(route + "/" + str(object_id), headers=current)).status_code == 409
    assert (await client.get(route, headers=current)).status_code == 409
    assert (await client.post(route, headers=receipt, json=payload)).status_code == 409
    # Restored data must not introduce an alternate identity into exact lookup.
    params = {"alias": "corrupted"} if family == "aliases" else payload
    resolved = await client.get(prefix + "/" + family + "/resolve", headers=current, params=params)
    assert resolved.status_code == (409 if family == "aliases" else 404)


@pytest.mark.parametrize("denied_entity", ["catalog.brand", "catalog.master_alias"])
async def test_resolution_cannot_disclose_hidden_activity(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    denied_entity: str,
) -> None:
    company, user, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    created = await client.post(
        owner + "/aliases", headers=command_headers(current), json={"alias": "Active"}
    )
    assert created.status_code == 201
    await policy(factory, tenant_a, company, user, denied_entity, "is_active", "read")
    for alias in ("Active", "absent"):
        response = await client.get(
            prefix + "/aliases/resolve", headers=current, params={"alias": alias}
        )
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("field", ["entity_type", "target_id"])
async def test_hidden_mapping_membership_protects_all_access_paths(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    field: str,
) -> None:
    company, user, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    receipt = command_headers(current)
    body = {"alias": "A"}
    created = await client.post(owner + "/aliases", headers=receipt, json=body)
    assert created.status_code == 201
    detail = owner + "/aliases/" + created.json()["id"]
    await policy(factory, tenant_a, company, user, "catalog.master_alias", field, "read")
    for path in (owner + "/aliases", detail):
        assert (await client.get(path, headers=current)).status_code == 403
    assert (
        await client.get(prefix + "/aliases/resolve", headers=current, params=body)
    ).status_code == 403
    assert (await client.post(owner + "/aliases", headers=receipt, json=body)).status_code == 403
    assert (
        await client.post(
            detail + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 403
    assert (
        await client.get(
            owner + "/usage", headers=current, params={"relation": "catalog.master_alias.target_id"}
        )
    ).status_code == 403


async def test_reference_commands_cannot_probe_hidden_owner_activity(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, owner, _ = await setup_owner(client, factory, tenant_a)
    receipt = command_headers(current)
    created = await client.post(owner + "/aliases", headers=receipt, json={"alias": "A"})
    assert created.status_code == 201
    await policy(factory, tenant_a, company, user, "catalog.brand", "is_active", "read")
    requests = (
        (owner + "/aliases", command_headers(current), {"alias": "B"}),
        (owner + "/aliases", receipt, {"alias": "A"}),
        (
            owner + "/aliases/" + created.json()["id"] + "/activate",
            command_headers(current),
            {"expected_version": 1},
        ),
    )
    for path, auth, body in requests:
        response = await client.post(path, headers=auth, json=body)
        assert response.status_code == 403, response.text
