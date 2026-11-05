"""Authoritative synthetic Identity capabilities for product integrity workflows."""

import uuid
from collections.abc import Collection

from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.source_factories import all_facts
from tests.test_classification_api import setup_source


async def features(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    enabled: Collection[str],
    *,
    version: int = 3,
) -> None:
    records = tuple(
        SnapshotRecord(
            kind="feature",
            id=uuid7(),
            data={
                "company_id": str(company),
                "feature_key": key,
                "is_enabled": True,
                "locked_at": None,
            },
        )
        for key in sorted(enabled)
    )
    await setup_source(
        factory, tenant, company, user, version=version, facts=(*all_facts(company, user), *records)
    )
