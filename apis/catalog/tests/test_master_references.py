"""Company-owned mapping identity and authorization regressions."""

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.test_api import headers
from tests.test_classification_api import create, setup_source
from tests.test_commercial_api import command_headers


async def setup_owner(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], str, str]:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant, company, user)
    current = headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            "brand.read",
            "brand.manage",
            "master_alias.read",
            "master_alias.manage",
            "master_external_key.read",
            "master_external_key.manage",
        ],
    )
    result = await create(client, company, current, "brands", {"code": "ACME", "name": "Acme"})
    assert result.status_code == 201, result.text
    prefix = f"/v1/companies/{company}/masters/catalog.brand"
    return company, user, current, prefix + "/" + result.json()["id"], prefix


@pytest.mark.parametrize(
    "family,payload",
    [
        ("aliases", {"alias": "  Stra\u00dfe  Parts  "}),
        ("external-keys", {"source_namespace": "legacy.erp", "external_key": "000AbC  42"}),
    ],
)
async def test_master_reference_identity_lifecycle_and_exact_resolution(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    family: str,
    payload: dict[str, str],
) -> None:
    company, _, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    route = owner + "/" + family
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=payload)
    assert created.status_code == 201, created.text
    record = created.json()
    detail = route + "/" + record["id"]
    assert (await client.post(route, headers=receipt, json=payload)).headers[
        "Idempotency-Replayed"
    ] == "true"
    if family == "aliases":
        assert record["alias"] == "Stra\u00dfe  Parts"
        assert record["canonical_value"] == "strasse parts"
        lookup = {"alias": "STRASSE PARTS"}
        assert (
            await client.post(route, headers=command_headers(current), json=lookup)
        ).status_code == 409
        page = await client.get(route, headers=current, params={"q": "STRASSE", "limit": 1})
    else:
        assert record["external_key"] == "000AbC  42"
        lookup = payload
        assert (await client.get(route, headers=current, params={"q": "000AbC"})).status_code == 422
        assert (
            await client.get(
                route, headers=current, params={"external_key": payload["external_key"]}
            )
        ).status_code == 422
        page = await client.get(route, headers=current, params=payload)
        wrong = {**payload, "external_key": "000abc 42"}
        assert (
            await client.get(prefix + "/" + family + "/resolve", headers=current, params=wrong)
        ).status_code == 404
    assert page.status_code == 200 and page.json()["items"][0]["id"] == record["id"], page.text
    resolved = await client.get(prefix + "/" + family + "/resolve", headers=current, params=lookup)
    assert (
        resolved.status_code == 200 and resolved.json()["target_id"] == record["target_id"]
    ), resolved.text
    assert (
        await client.post(
            detail + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.get(prefix + "/" + family + "/resolve", headers=current, params=lookup)
    ).status_code == 404
    # Retirement retains the unique identity; imports cannot accidentally claim a new owner.
    assert (
        await client.post(route, headers=command_headers(current), json=payload)
    ).status_code == 409
    other = await create(client, company, current, "brands", {"code": "OTHER", "name": "Other"})
    foreign_route = prefix + "/" + other.json()["id"] + "/" + family
    assert (
        await client.post(foreign_route, headers=command_headers(current), json=payload)
    ).status_code == 409
    assert (
        await client.get(foreign_route + "/" + record["id"], headers=current)
    ).status_code == 403
    assert (
        await client.post(
            detail + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    assert (
        await client.post(
            detail + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409
    assert (await client.get(detail, headers=current)).json()["row_version"] == 3
    # No retarget/update API exists for either identity family.
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"target_id": other.json()["id"]}
        )
    ).status_code == 405


@pytest.mark.parametrize(
    "family,payload",
    [
        ("aliases", {"alias": "Acme parts"}),
        ("external-keys", {"source_namespace": "legacy.erp", "external_key": "000123"}),
    ],
)
async def test_every_reference_operation_requires_owner_and_mapping_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    family: str,
    payload: dict[str, str],
) -> None:
    company, user, current, owner, prefix = await setup_owner(client, factory, tenant_a)
    route = owner + "/" + family
    created = await client.post(route, headers=command_headers(current), json=payload)
    assert created.status_code == 201, created.text
    detail = route + "/" + created.json()["id"]
    calls: tuple[tuple[str, str, dict[str, Any] | None, dict[str, str] | None], ...] = (
        ("GET", route, None, None),
        ("POST", route, payload, None),
        ("GET", detail, None, None),
        ("POST", detail + "/activate", {"expected_version": 1}, None),
        ("POST", detail + "/deactivate", {"expected_version": 1}, None),
        ("GET", prefix + "/" + family + "/resolve", None, payload),
    )
    denied = headers(company, tenant=tenant_a, user=user, permission="item.read")
    owner_only = headers(
        company, tenant=tenant_a, user=user, permission=["brand.read", "brand.manage"]
    )
    for method, path, body, params in calls:
        assert (await client.request(method, path, json=body, params=params)).status_code == 401
        for authority in (denied, owner_only):
            result = await client.request(
                method, path, headers=command_headers(authority), json=body, params=params
            )
            assert result.status_code == 403, result.text
