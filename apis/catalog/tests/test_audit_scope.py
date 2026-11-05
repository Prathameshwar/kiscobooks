"""Every emitted Catalog command event retains its authoritative company scope."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.audit_contract import AUDIT_EVENTS
from catalog.models import IdempotencyKey, Outbox, UnitOfMeasure
from tests.test_api import headers
from tests.test_classification_api import create
from tests.test_unit_api import UNIT_BODY, seed_context


async def test_all_implemented_master_events_have_company_scope(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    user = uuid7()
    companies = [uuid7(), uuid7()]
    owners: dict[str, uuid.UUID] = {}
    for company in companies:
        await seed_context(factory, tenant_a, company, user)
        auth = headers(
            company,
            tenant=tenant_a,
            user=user,
            permission=[
                "unit.manage",
                "pack_type.manage",
                "item_group.manage",
                "item_category.manage",
                "category_scheme.manage",
                "category_scheme.read",
            ],
        )
        root = f"/v1/companies/{company}/"

        async def create(
            resource: str,
            body: dict[str, Any],
            *,
            root: str = root,
            auth: dict[str, str] = auth,
            company: uuid.UUID = company,
        ) -> dict[str, Any]:
            request_headers = {**auth, "Idempotency-Key": str(uuid7())}
            response = await client.post(root + resource, json=body, headers=request_headers)
            assert response.status_code == 201, response.text
            replay = await client.post(root + resource, json=body, headers=request_headers)
            assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
            result: dict[str, Any] = response.json()
            owners[result["id"]] = company
            return result

        unit = await create("units", UNIT_BODY)
        await create("pack-types", {"code": "BOX", "name": "Private pack label"})
        await create(
            "unit-conversions",
            {
                "from_unit_id": unit["id"],
                "canonical_unit_id": unit["id"],
                "numerator": "1",
                "denominator": "1",
            },
        )
        await create(
            "unit-tax-codes",
            {
                "unit_id": unit["id"],
                "jurisdiction": "TEST",
                "official_code": "EA",
                "valid_from": "2025-01-01",
            },
        )
        await create(
            "item-groups",
            {
                "code": "A",
                "name": "Private group label",
                "valid_from": "2025-01-01",
            },
        )
        scheme = await create(
            "category-schemes",
            {
                "code": "S",
                "name": "Private scheme label",
                "membership_mode": "SINGLE",
            },
        )
        await create(
            "item-categories",
            {
                "code": "C",
                "name": "Private category label",
                "scheme_id": scheme["id"],
            },
        )
    async with factory() as db:
        rows = list(await db.scalars(select(Outbox)))
    assert (
        len(rows) == 16
    )  # Seven resources plus a group-parent edge per company; no replay events.
    assert {row.payload.get("company_id") for row in rows} == {str(c) for c in companies}
    for row in rows:
        assert row.event_type in AUDIT_EVENTS
        assert row.tenant_id == tenant_a and row.payload["actor_user_id"] == str(user)
        if str(row.aggregate_id) in owners:
            assert row.payload["company_id"] == str(owners[str(row.aggregate_id)])
        assert "Private" not in str(row.payload)


async def test_hierarchy_moves_have_publishable_audit_routes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    auth = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "item_group.manage",
            "item_group.move",
            "item_group.read",
            "category_scheme.manage",
            "category_scheme.read",
            "item_category.manage",
            "item_category.move",
            "item_category.read",
        ],
    )
    root = f"/v1/companies/{company}/"
    group_a = await create(
        client,
        company,
        auth,
        "item-groups",
        {
            "code": "A",
            "name": "A",
            "valid_from": "2025-01-01",
        },
    )
    group_b = await create(
        client,
        company,
        auth,
        "item-groups",
        {
            "code": "B",
            "name": "B",
            "valid_from": "2025-01-01",
        },
    )
    assert group_a.status_code == group_b.status_code == 201
    moved_group = await client.post(
        root + "item-groups/" + group_b.json()["id"] + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": group_b.json()["policy_generation"],
            "parent_group_id": group_a.json()["id"],
            "effective_from": (utcnow().date() + dt.timedelta(days=2)).isoformat(),
        },
    )
    assert moved_group.status_code == 200, moved_group.text
    scheme = await create(
        client,
        company,
        auth,
        "category-schemes",
        {
            "code": "S",
            "name": "S",
            "membership_mode": "SINGLE",
        },
    )
    assert scheme.status_code == 201
    a = await create(
        client,
        company,
        auth,
        "item-categories",
        {
            "code": "A",
            "name": "A",
            "scheme_id": scheme.json()["id"],
        },
    )
    b = await create(
        client,
        company,
        auth,
        "item-categories",
        {
            "code": "B",
            "name": "B",
            "scheme_id": scheme.json()["id"],
        },
    )
    assert a.status_code == b.status_code == 201
    moved_category = await client.post(
        root + "item-categories/" + b.json()["id"] + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": b.json()["policy_generation"],
            "parent_id": a.json()["id"],
        },
    )
    assert moved_category.status_code == 200, moved_category.text
    async with factory() as db:
        rows = list(await db.scalars(select(Outbox)))
    emitted = {row.event_type for row in rows}
    assert {"catalog.item_group.move", "catalog.item_category.move"} <= emitted
    assert emitted <= AUDIT_EVENTS
    assert all(row.payload["company_id"] == str(company) for row in rows)


async def test_unregistered_event_rolls_back_entity_receipt_and_outbox(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    auth = headers(company, tenant=tenant_a, user=user, permission="unit.manage")
    monkeypatch.setattr("catalog.events.audit_contract.AUDIT_EVENTS", frozenset())
    response = await client.post(
        f"/v1/companies/{company}/units",
        json=UNIT_BODY,
        headers={**auth, "Idempotency-Key": str(uuid7())},
    )
    assert response.status_code == 500
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(UnitOfMeasure.id).limit(1)) is None
            assert await db.scalar(select(IdempotencyKey.id).limit(1)) is None
            assert await db.scalar(select(Outbox.id).limit(1)) is None
