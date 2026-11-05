from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, Outbox
from tests.test_unit_api import UNIT_BODY, access, policy, seed_context


async def unit(
    client: httpx.AsyncClient,
    root: str,
    write: dict[str, str],
    code: str,
    *,
    dimension: str = "MASS",
) -> str:
    result = await client.post(
        root + "/units",
        json={
            **UNIT_BODY,
            "code": code,
            "dimension": dimension,
            "decimal_places": 3,
            "quantity_increment": "0.001",
        },
        headers={**write, "Idempotency-Key": code},
    )
    assert result.status_code == 201, result.text
    return str(result.json()["id"])


pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_canonical_conversions_require_direct_same_dimension_roots(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}"
    write = access(tenant_a, company, user, "unit.manage", key="conversion")
    read = access(tenant_a, company, user, "unit.read")
    kg, gram, tonne, piece = [
        await unit(client, root, write, code, dimension=dimension)
        for code, dimension in [("KG", "MASS"), ("G", "MASS"), ("TONNE", "MASS"), ("EA", "COUNT")]
    ]
    route = root + "/unit-conversions"
    body: dict[str, Any] = {
        "from_unit_id": gram,
        "canonical_unit_id": kg,
        "numerator": 2,
        "denominator": 2000,
    }
    assert (await client.post(route, json=body, headers=write)).status_code == 422
    root_body = {**body, "from_unit_id": kg, "numerator": 1, "denominator": 1}
    root_result = await client.post(
        route, json=root_body, headers={**write, "Idempotency-Key": "root"}
    )
    assert root_result.status_code == 201, root_result.text
    created = await client.post(route, json=body, headers=write)
    assert created.status_code == 201, created.text
    assert created.json()["numerator"] == "1" and created.json()["denominator"] == "1000"
    assert (await client.get(created.headers["location"], headers=read)).json() == created.json()
    assert (await client.post(route, json=body, headers=write)).headers[
        "Idempotency-Replayed"
    ] == "true"
    assert (
        await client.post(route, json=body, headers={**write, "Idempotency-Key": "duplicate"})
    ).status_code == 409
    cases: list[dict[str, Any]] = [
        {"from_unit_id": tonne, "canonical_unit_id": gram},
        {"from_unit_id": piece},
        {"numerator": 0},
        {"numerator": True},
        {"from_unit_id": tonne, "canonical_unit_id": tonne, "numerator": 2, "denominator": 1},
    ]
    for number, changes in enumerate(cases):
        response = await client.post(
            route,
            json={**body, **changes},
            headers={**write, "Idempotency-Key": f"invalid-{number}"},
        )
        assert response.status_code == 422, response.text
    first = await client.get(route, params={"limit": 1, "sort": "-id"}, headers=read)
    assert first.status_code == 200 and first.json()["page"]["has_more"] is True
    second = await client.get(
        route,
        params={"limit": 1, "sort": "-id", "cursor": first.json()["page"]["next_cursor"]},
        headers=read,
    )
    assert second.status_code == 200 and second.json()["page"]["has_more"] is False
    assert (
        len((await client.get(route, params={"from_unit_id": gram}, headers=read)).json()["items"])
        == 1
    )
    assert (
        len(
            (await client.get(route, params={"canonical_unit_id": kg}, headers=read)).json()[
                "items"
            ]
        )
        == 2
    )
    assert (await client.get(route, params={"q": "KG"}, headers=read)).status_code == 422
    assert (await client.get(route, params={"sort": "numerator"}, headers=read)).status_code == 422
    assert (
        await client.patch(created.headers["location"], json=body, headers=write)
    ).status_code == 405


async def test_official_code_effective_dates_closure_and_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}"
    write = access(tenant_a, company, user, "unit.manage", key="mapping")
    read = access(tenant_a, company, user, "unit.read")
    unit_id = await unit(client, root, write, "KG")
    route = root + "/unit-tax-codes"
    body = {
        "unit_id": unit_id,
        "jurisdiction": "IN.GST",
        "official_code": "KGS",
        "valid_from": "2025-01-01",
    }
    created = await client.post(route, json=body, headers=write)
    assert created.status_code == 201, created.text
    detail_route = created.headers["location"]
    assert (await client.get(detail_route, headers=read)).json() == created.json()
    assert (await client.post(route, json=body, headers=write)).headers[
        "Idempotency-Replayed"
    ] == "true"
    overlap = await client.post(
        route,
        json={**body, "valid_from": "2025-02-01"},
        headers={**write, "Idempotency-Key": "overlap"},
    )
    assert overlap.status_code == 409
    close = {"expected_valid_to": None, "valid_to": "2025-01-31"}
    closed = await client.post(
        detail_route + "/close", json=close, headers={**write, "Idempotency-Key": "close"}
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["valid_to"] == "2025-01-31"
    assert (
        await client.post(
            detail_route + "/close", json=close, headers={**write, "Idempotency-Key": "close"}
        )
    ).status_code == 200
    assert (
        await client.post(
            detail_route + "/close", json=close, headers={**write, "Idempotency-Key": "stale-close"}
        )
    ).status_code == 409
    for end in ["2024-12-31", "2025-02-01"]:
        assert (
            await client.post(
                detail_route + "/close",
                json={"expected_valid_to": "2025-01-31", "valid_to": end},
                headers={**write, "Idempotency-Key": end},
            )
        ).status_code == 422
    assert (
        await client.post(
            detail_route + "/close",
            json={"expected_valid_to": "2025-01-31", "valid_to": "2025-01-31"},
            headers={**write, "Idempotency-Key": "noop"},
        )
    ).status_code == 200
    adjacent = await client.post(
        route,
        json={**body, "valid_from": "2025-02-01", "official_code": "KILO"},
        headers={**write, "Idempotency-Key": "next"},
    )
    assert adjacent.status_code == 201, adjacent.text
    for day, expected in [("2024-12-31", []), ("2025-01-31", ["KGS"]), ("2025-02-01", ["KILO"])]:
        listed = await client.get(
            route,
            params={"unit_id": unit_id, "jurisdiction": "IN.GST", "valid_at": day},
            headers=read,
        )
        assert listed.status_code == 200, listed.text
        assert [row["official_code"] for row in listed.json()["items"]] == expected
    assert len((await client.get(route, params={"q": "KG"}, headers=read)).json()["items"]) == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(Outbox)))) == 4
            assert len(list(await db.scalars(select(IdempotencyKey)))) == 5


@pytest.mark.parametrize("mapping", [False, True])
async def test_relation_authority_scope_defaults_and_current_replay(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    mapping: bool,
) -> None:
    company, other, foreign, user = uuid7(), uuid7(), uuid7(), uuid7()
    for tenant, target in [(tenant_a, company), (tenant_a, other), (tenant_b, foreign)]:
        await seed_context(factory, tenant, target, user)
    root = f"/v1/companies/{company}"
    write = access(tenant_a, company, user, "unit.manage", key="create")
    read = access(tenant_a, company, user, "unit.read")
    unit_id = await unit(client, root, write, "KG")
    resource = "unit-tax-codes" if mapping else "unit-conversions"
    route = root + "/" + resource
    entity = "catalog.unit_tax_code" if mapping else "catalog.unit_conversion"
    body: dict[str, Any] = (
        {
            "unit_id": unit_id,
            "jurisdiction": "IN.GST",
            "official_code": "KGS",
            "valid_from": "2025-01-01",
        }
        if mapping
        else {
            "from_unit_id": unit_id,
            "canonical_unit_id": unit_id,
            "numerator": 1,
            "denominator": 1,
        }
    )
    assert (
        await client.post(route, json=body, headers={"Idempotency-Key": "anonymous"})
    ).status_code == 401
    assert (
        await client.post(route, json=body, headers={**read, "Idempotency-Key": "read-only"})
    ).status_code == 403
    created = await client.post(route, json=body, headers=write)
    assert created.status_code == 201, created.text
    object_id = created.json()["id"]
    for tenant, target, expected in [(tenant_a, other, 403), (tenant_b, foreign, 404)]:
        scoped = access(tenant, target, user, "unit.read")
        assert (
            await client.get(f"/v1/companies/{target}/{resource}/{object_id}", headers=scoped)
        ).status_code == expected
        scoped_write = access(tenant, target, user, "unit.manage", key="bad-ref")
        assert (
            await client.post(f"/v1/companies/{target}/{resource}", json=body, headers=scoped_write)
        ).status_code == expected
    hidden = "valid_to" if mapping else "numerator"
    await seed_context(
        factory, tenant_a, company, user, (policy(user, hidden, "read", entity=entity),), version=3
    )
    replay = await client.post(route, json=body, headers=write)
    assert replay.status_code == 201 and hidden not in replay.json()
    assert hidden not in (await client.get(created.headers["location"], headers=read)).json()
    assert hidden not in (await client.get(route, headers=read)).json()["items"][0]
    if mapping:
        assert (
            await client.get(route, params={"valid_at": "2025-01-02"}, headers=read)
        ).status_code == 403
    await seed_context(
        factory, tenant_a, company, user, (policy(user, hidden, "write", entity=entity),), version=4
    )
    assert (await client.post(route, json=body, headers=write)).status_code == 403
    if mapping:
        assert (
            await client.post(
                created.headers["location"] + "/close",
                json={"expected_valid_to": None, "valid_to": "2025-01-31"},
                headers={**write, "Idempotency-Key": "denied-close"},
            )
        ).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(Outbox)))) == 2


async def test_exact_conversion_preview_and_large_ratio_wire_values(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}"
    write = access(tenant_a, company, user, "unit.manage", key="relation")
    read = access(tenant_a, company, user, "unit.read")
    kg, gram, large, independent = [
        await unit(client, root, write, code) for code in ("KG", "G", "LARGE", "OTHER")
    ]
    count = await unit(client, root, write, "EA", dimension="COUNT")
    for source, canonical, numerator, denominator in [
        (kg, kg, "1", "1"),
        (gram, kg, "1", "1000"),
        (large, kg, "9007199254740993", "1"),
        (independent, independent, "1", "1"),
    ]:
        relation = await client.post(
            root + "/unit-conversions",
            json={
                "from_unit_id": source,
                "canonical_unit_id": canonical,
                "numerator": numerator,
                "denominator": denominator,
            },
            headers={**write, "Idempotency-Key": source},
        )
        assert relation.status_code == 201, relation.text
        assert relation.json()["numerator"] == numerator
        assert relation.json()["denominator"] == denominator
    route = root + "/units/convert"
    for source, target, entered, expected in [
        (gram, kg, "1250", "1.2500"),
        (kg, gram, "0.125", "125.0000"),
        (gram, gram, "0", "0.0000"),
    ]:
        converted = await client.post(
            route,
            json={"from_unit_id": source, "to_unit_id": target, "quantity": entered},
            headers=read,
        )
        assert converted.status_code == 200, converted.text
        assert converted.json()["quantity"] == expected
    for source, target, entered in [
        (gram, kg, "0.001"),
        (gram, kg, "0.0001"),
        (gram, count, "1"),
        (gram, independent, "1"),
        (gram, kg, "-1"),
    ]:
        assert (
            await client.post(
                route,
                json={"from_unit_id": source, "to_unit_id": target, "quantity": entered},
                headers=read,
            )
        ).status_code == 422
    unlinked = await unit(client, root, write, "UNLINKED")
    assert (
        await client.post(
            route, json={"from_unit_id": kg, "to_unit_id": unlinked, "quantity": "1"}, headers=read
        )
    ).status_code == 422
    inactive = await client.post(
        root + "/units/" + unlinked + "/deactivate",
        json={"expected_version": 1},
        headers={**write, "Idempotency-Key": "deactivate"},
    )
    assert inactive.status_code == 200
    assert (
        await client.post(
            route, json={"from_unit_id": kg, "to_unit_id": unlinked, "quantity": "1"}, headers=read
        )
    ).status_code == 409
    for part in ("0", "1.5", "1e3", "9223372036854775808", "9" * 20):
        assert (
            await client.post(
                root + "/unit-conversions",
                json={
                    "from_unit_id": kg,
                    "canonical_unit_id": kg,
                    "numerator": part,
                    "denominator": "1",
                },
                headers={**write, "Idempotency-Key": "bad-ratio"},
            )
        ).status_code == 422
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        (policy(user, "numerator", "read", entity="catalog.unit_conversion"),),
        version=3,
    )
    assert (
        await client.post(
            route, json={"from_unit_id": kg, "to_unit_id": gram, "quantity": "1"}, headers=read
        )
    ).status_code == 403
    await seed_context(
        factory, tenant_a, company, user, (policy(user, "quantity_increment", "read"),), version=4
    )
    assert (
        await client.post(
            route, json={"from_unit_id": kg, "to_unit_id": kg, "quantity": "1"}, headers=read
        )
    ).status_code == 403
