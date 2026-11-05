import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.returns import ReturnPolicyCondition, ReturnPolicyRevision
from tests.return_factories import auth, seed_policy
from tests.test_commercial_api import command_headers


async def test_return_reactivation_rejects_incomplete_published_conditions(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    parent_id, revision_id = await seed_policy(factory, tenant_a, company)
    master = f"/v1/companies/{company}/return-policies/{parent_id}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ReturnPolicyRevision, revision_id)
            assert revision is not None
            revision.published_at = utcnow()
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            condition = await db.scalar(
                select(ReturnPolicyCondition).where(
                    ReturnPolicyCondition.revision_id == revision_id,
                    ReturnPolicyCondition.condition_code == "UNUSED",
                )
            )
            assert condition is not None
            await db.delete(condition)
    response = await client.post(
        master + "/activate", headers=command_headers(current), json={"expected_version": 2}
    )
    assert response.status_code == 409, response.text
    assert (await client.get(master, headers=current)).json()["is_active"] is False
