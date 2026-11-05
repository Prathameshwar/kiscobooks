"""Retained compound meanings must survive unit administration unchanged."""

import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CompoundUnitComponent, Outbox
from tests.test_commercial_api import command_headers
from tests.test_unit_api import UNIT_BODY, access, seed_context


@pytest.mark.parametrize("pack", [False, True])
async def test_invalid_merged_master_settings_return_validation_without_changes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    pack: bool,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    auth = access(tenant_a, company, user, "pack_type.manage" if pack else "unit.manage")
    root = f"/v1/companies/{company}/" + ("pack-types" if pack else "units")
    created = await client.post(
        root,
        headers=command_headers(auth),
        json={"code": "BOX", "name": "Box"} if pack else UNIT_BODY,
    )
    assert created.status_code == 201, created.text
    path = root + "/" + created.json()["id"]
    field = "name" if pack else "quantity_increment"
    invalid = {"name": "   "} if pack else {"quantity_increment": "0.5"}
    result = await client.patch(
        path, headers=command_headers(auth), json={"expected_version": 1, **invalid}
    )
    assert result.status_code == 422, result.text
    assert field in result.json()["error"]["fields"]
    valid = await client.patch(
        path, headers=command_headers(auth), json={"expected_version": 1, "name": "Corrected label"}
    )
    assert valid.status_code == 200 and valid.json()["row_version"] == 2, valid.text


@pytest.mark.parametrize("endpoint", ["parent", "child"])
@pytest.mark.parametrize("operation", ["quantity", "deactivate"])
async def test_compound_references_protect_unit_meaning_and_allow_labels(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    endpoint: str,
    operation: str,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    auth = access(tenant_a, company, user, "unit.manage")
    root = f"/v1/companies/{company}/units"
    identities = {}
    for kind in ("parent", "child"):
        created = await client.post(
            root, headers=command_headers(auth), json={**UNIT_BODY, "code": kind.upper()}
        )
        assert created.status_code == 201, created.text
        identities[kind] = uuid.UUID(created.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                CompoundUnitComponent(
                    tenant_id=tenant_a,
                    company_id=company,
                    parent_unit_id=identities["parent"],
                    child_unit_id=identities["child"],
                    quantity=Decimal("12"),
                    ordinal=1,
                )
            )
        async with factory() as db:
            audit_before = await db.scalar(select(func.count(Outbox.id)))
    path = root + "/" + str(identities[endpoint])
    if operation == "quantity":
        result = await client.patch(
            path,
            headers=command_headers(auth),
            json={
                "expected_version": 1,
                "decimal_places": 2,
                "quantity_increment": "0.01",
            },
        )
    else:
        result = await client.post(
            path + "/deactivate", headers=command_headers(auth), json={"expected_version": 1}
        )
    assert result.status_code == 409, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == audit_before
    headers = command_headers(auth)
    body = {"expected_version": 1, "name": "Corrected descriptive label"}
    renamed = await client.patch(path, headers=headers, json=body)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["row_version"] == 2
    replay = await client.patch(path, headers=headers, json=body)
    assert replay.status_code == 200 and replay.json() == renamed.json()
