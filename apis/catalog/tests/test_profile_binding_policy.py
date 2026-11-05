import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, Outbox
from catalog.models.commercial import ProductTypeRevision
from tests.commercial_factories import auth
from tests.profile_binding_factories import CASES, GOODS, ProfileCase, publish_seed, setup_type
from tests.source_factories import all_facts
from tests.test_commercial_api import command_headers


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.field)
async def test_native_binding_denies_protect_create_patch_publish_and_retained_replay(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    case: ProfileCase,
) -> None:
    company, user, current, master, _, revision = await setup_type(client, factory, tenant_a, case)
    await publish_seed(factory, tenant_a, case, revision)
    route = master + "/revisions"
    payload = {**GOODS, case.field: str(revision)}
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=payload)
    assert created.status_code == 201
    detail = route + "/" + created.json()["id"]
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.product_type_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": case.field,
            "access": "write",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    replay_headers = {**current, "Idempotency-Key": receipt["Idempotency-Key"]}
    assert (await client.post(route, headers=replay_headers, json=payload)).status_code == 403
    assert (
        await client.post(route, headers=command_headers(current), json=payload)
    ).status_code == 403
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 1, case.field: None}
        )
    ).status_code == 403
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductTypeRevision.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 2
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 2
    # An absent optional default is unaffected by a deny on material binding writes.
    unbound = await client.post(route, headers=command_headers(current), json=GOODS)
    assert unbound.status_code == 201, unbound.text
    assert (
        await client.post(
            route + "/" + unbound.json()["id"] + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    hidden = SnapshotRecord(kind="field_policy", id=deny.id, data={**deny.data, "access": "read"})
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, hidden))
    detail_response = await client.get(detail, headers=current)
    assert detail_response.status_code == 200 and case.field not in detail_response.json()
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.product_type_revision/field-set", headers=current
    )
    assert metadata.status_code == 200
    assert case.field not in {item["key"] for item in metadata.json()["fields"]}


@pytest.mark.parametrize("field", [*(case.field for case in CASES), "attribute_set_revision_id"])
async def test_denied_binding_cannot_probe_reference_availability(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    field: str,
) -> None:
    company, user, current, master, _, _ = await setup_type(client, factory, tenant_a, CASES[0])
    route = master + "/revisions"
    created = await client.post(route, headers=command_headers(current), json=GOODS)
    assert created.status_code == 201
    detail = route + "/" + created.json()["id"]
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.product_type_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": field,
            "access": "write",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    for method, path, payload in (
        ("POST", route, {**GOODS, field: str(uuid7())}),
        ("PATCH", detail, {"expected_version": 1, field: str(uuid7())}),
    ):
        response = await client.request(
            method, path, headers=command_headers(current), json=payload
        )
        assert response.status_code == 403, response.text


async def test_binding_preflight_uses_the_resulting_row_version(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    case = CASES[1]
    company, user, current, master, _, revision = await setup_type(client, factory, tenant_a, case)
    await publish_seed(factory, tenant_a, case, revision)
    route = master + "/revisions"
    created = await client.post(route, headers=command_headers(current), json=GOODS)
    assert created.status_code == 201
    detail = route + "/" + created.json()["id"]
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.product_type_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": case.field,
            "access": "write",
            "condition": {"field": "row_version", "cmp": "gt", "value": 1},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    for target in (uuid7(), revision):
        response = await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, case.field: str(target)},
        )
        assert response.status_code == 403, response.text
    unchanged = await client.get(detail, headers=current)
    assert unchanged.status_code == 200
    assert unchanged.json()["row_version"] == 1
    assert unchanged.json()[case.field] is None
    # Creating the initial revision remains allowed by this conditional policy.
    allowed = await client.post(
        route, headers=command_headers(current), json={**GOODS, case.field: str(revision)}
    )
    assert allowed.status_code == 201, allowed.text
