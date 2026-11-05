import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.profiles import IdentifierProfileRequirement
from catalog.models.returns import ReturnPolicyCondition
from tests.profile_binding_factories import CASES, GOODS, ProfileCase, publish_seed, setup_type
from tests.profile_factories import seed_identifier_profile
from tests.test_commercial_api import command_headers


@pytest.mark.parametrize("case", [CASES[0], CASES[2]], ids=lambda c: c.field)
async def test_missing_published_members_block_type_publication_and_reactivation(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    case: ProfileCase,
) -> None:
    company, _, current, master, _, revision_id = await setup_type(client, factory, tenant_a, case)
    payload: dict[str, Any] = {**GOODS, case.field: str(revision_id)}
    child_model: type[IdentifierProfileRequirement] | type[ReturnPolicyCondition]
    if case.field == "inventory_template_revision_id":
        identifier = await seed_identifier_profile(factory, tenant_a, company)
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                revision = await db.get(InventoryProfileTemplateRevision, revision_id)
                assert revision is not None
                revision.serial_tracking = True
                revision.identifier_profile_id = identifier
        payload["tracking_modes"] = ["SERIAL"]
        child_model = IdentifierProfileRequirement
    else:
        child_model = ReturnPolicyCondition
    await publish_seed(factory, tenant_a, case, revision_id)
    route = master + "/revisions"
    created = await client.post(route, headers=command_headers(current), json=payload)
    assert created.status_code == 201, created.text
    detail = route + "/" + created.json()["id"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            child = await db.scalar(
                select(child_model).where(child_model.company_id == company).limit(1)
            )
            assert isinstance(child, IdentifierProfileRequirement | ReturnPolicyCondition)
            original = {col.key: getattr(child, col.key) for col in child.__table__.columns}
            await db.delete(child)
    expected = 422 if case.field == "inventory_template_revision_id" else 409
    assert (
        await client.post(route, headers=command_headers(current), json=payload)
    ).status_code == expected
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == expected
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    rejected = await client.post(
        master + "/activate", headers=command_headers(current), json={"expected_version": 2}
    )
    assert rejected.status_code == 409, rejected.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(child_model(**original))
    assert (
        await client.post(
            master + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.field)
async def test_service_type_accepts_commercial_policies_but_rejects_physical_defaults(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    case: ProfileCase,
) -> None:
    _, _, current, master, _, revision_id = await setup_type(client, factory, tenant_a, case)
    changed = await client.patch(
        master, headers=command_headers(current), json={"expected_version": 1, "kind": "SERVICE"}
    )
    assert changed.status_code == 200
    await publish_seed(factory, tenant_a, case, revision_id)
    body = {
        "inventory_modes": ["NON_STOCK"],
        "tracking_modes": ["NONE"],
        "unit_dimensions": ["TIME"],
        case.field: str(revision_id),
    }
    response = await client.post(master + "/revisions", headers=command_headers(current), json=body)
    expected = (
        422 if case.field in {"inventory_template_revision_id", "handling_revision_id"} else 201
    )
    assert response.status_code == expected, response.text
