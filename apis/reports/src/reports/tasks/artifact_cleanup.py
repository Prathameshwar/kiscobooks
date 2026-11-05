"""Bounded temporary cleanup, retaining every completed object and its metadata."""

import argparse
import asyncio
import uuid
from typing import Any

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.models.export_artifacts import ReportExportArtifact
from reports.tasks import export_artifacts as artifacts
from reports.tasks.common import audit, get


async def cleanup(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
    after: uuid.UUID | None = None,
) -> dict[str, Any]:
    storage = await asyncio.to_thread(artifacts.store, settings)
    cleaned, failed = 0, 0
    with tenant_scope(tenant):
        async with factory() as db:
            records = await artifacts.candidates(db, company, after)
        for record in records:
            async with factory() as db, db.begin():
                key = await artifacts.cleanup_candidate(db, company, record.id)
            if key is None:
                continue
            try:
                removed = await asyncio.to_thread(storage.discard_temporary, key)
            except (OSError, ValueError):
                failed += 1
                continue
            async with factory() as db, db.begin():
                # State may advance to a later attempt; the old key is never reused.
                if await artifacts.cleanup_candidate(db, company, record.id) is None:
                    continue
                row = await get(db, company, ReportExportArtifact, record.id, lock=True)
                if row.temporary_cleaned_at is None:
                    row.temporary_cleaned_at = utcnow()
                    row.row_version += 1
                    audit(db, tenant, company, row.id, "temporary_cleaned")
            cleaned += int(removed)
    return {
        "examined": len(records),
        "removed_temporary_folders": cleaned,
        "failures": failed,
        "next_cursor": str(records[-1].id) if len(records) == 100 else None,
    }


async def execute(settings: Settings, tenant: uuid.UUID, company: uuid.UUID) -> None:
    from reports.tasks.enrollment import retained_scopes

    if (tenant, company) not in await retained_scopes(settings):
        raise PermissionDeniedError("artifact cleanup scope is not configured for this worker")
    engine = create_engine(settings.database_url)
    try:
        after = None
        while True:
            result = await cleanup(
                create_session_factory(engine, guarded=True), settings, tenant, company, after
            )
            if result["next_cursor"] is None:
                return
            after = uuid.UUID(result["next_cursor"])
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=uuid.UUID, required=True)
    parser.add_argument("--company", type=uuid.UUID, required=True)
    args = parser.parse_args()
    asyncio.run(execute(Settings.model_validate({}), args.tenant, args.company))


if __name__ == "__main__":
    main()
