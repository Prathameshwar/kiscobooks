import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox
from catalog.models.commercial import ProductTypeRevision
from tests.profile_binding_factories import CASES, GOODS, ProfileCase, publish_seed, setup_type
from tests.test_commercial_api import command_headers


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.field)
async def test_profile_binding_publication_optional_updates_and_dependency_lifecycle(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    case: ProfileCase,
) -> None:
    company, _, current, master, profile, revision = await setup_type(
        client, factory, tenant_a, case
    )
    route = master + "/revisions"
    payload: dict[str, Any] = {**GOODS, case.field: str(revision)}
    receipt = command_headers(current)
    assert (await client.post(route, headers=receipt, json=payload)).status_code == 409
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductTypeRevision.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == 1
    await publish_seed(factory, tenant_a, case, revision)
    created = await client.post(route, headers=receipt, json=payload)
    assert created.status_code == 201 and created.json()[case.field] == str(revision), created.text
    assert (await client.post(route, headers=receipt, json=payload)).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = route + "/" + created.json()["id"]
    noop = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, case.field: str(revision)},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 1, noop.text
    # Drafts also prevent retirement: saving a draft must not leave a dangling default.
    assert (
        await client.post(
            profile + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    cleared = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 1, case.field: None}
    )
    assert cleared.status_code == 200 and cleared.json()["row_version"] == 2
    assert cleared.json()[case.field] is None
    assert (
        await client.post(
            profile + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 2, case.field: str(revision)},
        )
    ).status_code == 409
    assert (
        await client.post(
            profile + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    rebound = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 2, case.field: str(revision)},
    )
    assert rebound.status_code == 200 and rebound.json()["row_version"] == 3
    published = await client.post(
        detail + "/publish", headers=command_headers(current), json={"expected_version": 3}
    )
    assert published.status_code == 200, published.text
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 4, case.field: None}
        )
    ).status_code == 409
    page = await client.get(route, headers=current, params={"published": True, "limit": 1})
    assert page.status_code == 200 and case.field not in page.json()["items"][0]
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.post(
            profile + "/deactivate", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 200
    assert (
        await client.post(
            master + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409
    assert (
        await client.post(
            profile + "/activate", headers=command_headers(current), json={"expected_version": 4}
        )
    ).status_code == 200
    activated = await client.post(
        master + "/activate", headers=command_headers(current), json={"expected_version": 2}
    )
    assert activated.status_code == 200, activated.text


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.field)
async def test_profile_binding_rejects_foreign_or_missing_target_on_create_and_patch(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    case: ProfileCase,
) -> None:
    _, _, current, master, _, _ = await setup_type(client, factory, tenant_a, case)
    route = master + "/revisions"
    created = await client.post(route, headers=command_headers(current), json=GOODS)
    assert created.status_code == 201
    detail = route + "/" + created.json()["id"]
    for tenant, expected in ((tenant_a, 403), (tenant_b, 404)):
        _, foreign = await case.seed(factory, tenant, uuid7())
        await publish_seed(factory, tenant, case, foreign)
        for method, path, payload in (
            ("POST", route, {**GOODS, case.field: str(foreign)}),
            ("PATCH", detail, {"expected_version": 1, case.field: str(foreign)}),
        ):
            rejected = await client.request(
                method, path, headers=command_headers(current), json=payload
            )
            assert rejected.status_code == expected, rejected.text
    assert (
        await client.post(
            route, headers=command_headers(current), json={**GOODS, case.field: str(uuid7())}
        )
    ).status_code == 404
    assert (await client.get(detail, headers=current)).json()["row_version"] == 1
