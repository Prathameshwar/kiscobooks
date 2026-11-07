import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.schemas.inventory_templates import InventoryRevisionInput
from catalog.tasks.inventory_templates import invalid_identifier
from tests.test_commercial_api import command_headers
from tests.test_inventory_template_api import setup_template


def test_serial_policy_requires_an_identifier_profile() -> None:
    with pytest.raises(ValidationFailedError, match="identifier profile"):
        InventoryRevisionInput(serial_tracking=True)


async def test_legacy_incomplete_serial_policy_cannot_be_published(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    _, _, current, master = await setup_template(client, factory, tenant_a)
    response = await client.post(master + "/revisions", headers=command_headers(current), json={})
    assert response.status_code == 201
    revision_id = uuid.UUID(response.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(InventoryProfileTemplateRevision, revision_id)
            assert revision is not None
            revision.serial_tracking = True
    result = await client.post(
        master + f"/revisions/{revision_id}/publish",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert result.status_code == 422, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            revision = await db.get(InventoryProfileTemplateRevision, revision_id)
            assert revision is not None and revision.published_at is None


async def test_invalid_identifier_includes_legacy_null_serial_profile(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    _, _, current, master = await setup_template(client, factory, tenant_a)
    response = await client.post(master + "/revisions", headers=command_headers(current), json={})
    revision_id = uuid.UUID(response.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(InventoryProfileTemplateRevision, revision_id)
            assert revision is not None
            revision.serial_tracking = True
            revision.published_at = utcnow()
        async with factory() as db:
            invalid = await db.scalar(
                select(InventoryProfileTemplateRevision.id).where(
                    InventoryProfileTemplateRevision.id == revision_id,
                    invalid_identifier(),
                )
            )
            assert invalid == revision_id
