import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db import create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.import_cleanup import cleanup_imports
from billing_platform.import_contracts import CommitImport, ImportAction
from billing_platform.import_models import (
    ImportArtifact,
    ImportChangeSetEffect,
    ImportJob,
    ImportJobAttempt,
    ImportJobRevision,
    ImportTemplateSnapshot,
)
from tests.models import TenantThing
from tests.test_import_framework import Adapter, invoke, row, stage


async def test_cleanup_expires_payloads_preserves_outcome_then_purges_history(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    factory = create_session_factory(factory.kw["bind"], guarded=True)
    first, second = Adapter(tenant_a), Adapter(tenant_b)
    job = await stage(factory, first, [row("one")])
    await stage(factory, second, [row("private")])
    ready = await invoke(factory, first, "validate", ImportAction(expected_version=1), job["id"])
    await invoke(
        factory,
        first,
        "commit",
        CommitImport(expected_version=ready["row_version"], review_digest=ready["review_digest"]),
        job["id"],
    )
    assert await cleanup_imports(factory, tenant_a, first.company, "example") == {
        "payload_jobs": 0,
        "templates": 0,
        "history_jobs": 0,
    }
    future = utcnow() + dt.timedelta(days=31)
    counts = await cleanup_imports(factory, tenant_a, first.company, "example", now=future)
    assert counts == {"payload_jobs": 1, "templates": 1, "history_jobs": 0}
    with tenant_scope(tenant_a):
        async with factory() as db:
            saved = await db.get(ImportJob, uuid.UUID(job["id"]))
            assert saved is not None and saved.state == "SUCCEEDED" and saved.completed_count == 1
            assert await db.scalar(select(ImportJobRevision.batch)) is None
            assert await db.scalar(select(ImportTemplateSnapshot.snapshot)) is None
            assert await db.scalar(select(ImportArtifact.content)) is None
            assert await db.scalar(select(func.count(ImportJobAttempt.id))) == 2
            assert await db.scalar(select(func.count(ImportChangeSetEffect.id))) == 1
            assert await db.scalar(select(func.count(TenantThing.id))) == 1
    assert await cleanup_imports(factory, tenant_a, first.company, "example", now=future) == {
        "payload_jobs": 0,
        "templates": 0,
        "history_jobs": 0,
    }
    purged = await cleanup_imports(
        factory, tenant_a, first.company, "example", now=future + dt.timedelta(days=366)
    )
    assert purged["history_jobs"] == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ImportJobAttempt.id))) == 0
            assert await db.scalar(select(func.count(ImportArtifact.id))) == 0
            assert await db.scalar(select(func.count(ImportChangeSetEffect.id))) == 1
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert await db.scalar(select(ImportJobRevision.batch)) is not None
            assert await db.scalar(select(ImportArtifact.content)) is not None


async def test_cleanup_covers_unvalidated_jobs_and_is_bounded(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    adapter = Adapter(tenant_a)
    for name in ("one", "two"):
        await stage(factory, adapter, [row(name)])
    future = utcnow() + dt.timedelta(days=400)
    first = await cleanup_imports(
        factory, tenant_a, adapter.company, "example", now=future, limit=1
    )
    assert first["payload_jobs"] == 1 and first["templates"] == 1 and first["history_jobs"] == 1
    second = await cleanup_imports(
        factory, tenant_a, adapter.company, "example", now=future, limit=1
    )
    assert second["payload_jobs"] == 1 and second["history_jobs"] == 1
