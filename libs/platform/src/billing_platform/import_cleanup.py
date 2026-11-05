"""Bounded retention sweeps; never deletes business effects or native receipts."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.import_engine import effects, pending_effects
from billing_platform.import_models import (
    ImportArtifact,
    ImportChangeSet,
    ImportJob,
    ImportJobAttempt,
    ImportJobDependency,
    ImportJobRecord,
    ImportJobRevision,
    ImportRecordIssue,
    ImportRecordResult,
    ImportTemplateSnapshot,
)
from billing_platform.outbox import audit_payload, emit


def evidence(
    db: AsyncSession, namespace: str, tenant: uuid.UUID, company: uuid.UUID, identifier: uuid.UUID
) -> None:
    entity = namespace + ".import_job"
    emit(
        db,
        aggregate_type=entity,
        aggregate_id=identifier,
        event_type=entity + ".cleanup",
        tenant_id=tenant,
        payload=audit_payload(
            action=entity + ".cleanup",
            entity_type=entity,
            entity_id=identifier,
            actor_user_id=None,
            company_id=company,
            category="system",
        ),
    )


async def cleanup_imports(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    namespace: str,
    *,
    limit: int = 50,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    if (
        not 1 <= limit <= 100
        or tenant.int == 0
        or company.int == 0
        or not re.fullmatch(r"[a-z]{1,32}", namespace)
    ):
        raise ValueError("cleanup requires bounded real owner scope")
    instant = now or utcnow()
    cutoff = instant - dt.timedelta(days=365)
    counts = {"payload_jobs": 0, "templates": 0, "history_jobs": 0}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            pending = (
                select(ImportJobRevision.id)
                .where(
                    ImportJobRevision.company_id == company,
                    ImportJobRevision.job_id == ImportJob.id,
                    ImportJobRevision.batch.is_not(None),
                )
                .exists()
            )
            jobs = list(
                await db.scalars(
                    select(ImportJob)
                    .where(
                        ImportJob.company_id == company, ImportJob.expires_at <= instant, pending
                    )
                    .order_by(ImportJob.expires_at, ImportJob.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in jobs:
                if job.state == "IMPORTING":
                    continue  # Reviewed commands still need admission; preserve their input.
                revisions = select(ImportJobRevision.id).where(
                    ImportJobRevision.company_id == company, ImportJobRevision.job_id == job.id
                )
                artifacts = await db.scalars(
                    select(ImportArtifact).where(
                        ImportArtifact.company_id == company,
                        ImportArtifact.revision_id.in_(revisions),
                    )
                )
                for artifact in artifacts:
                    artifact.content = None
                revision_rows = await db.scalars(
                    select(ImportJobRevision).where(
                        ImportJobRevision.company_id == company, ImportJobRevision.job_id == job.id
                    )
                )
                for revision in revision_rows:
                    revision.batch = None
                if job.state in {"STAGED", "READY", "INVALID", "VALIDATING"}:
                    job.state = "EXPIRED"
                job.review_digest, job.context_digest = None, None
                job.row_version += 1
                evidence(db, namespace, tenant, company, job.id)
                counts["payload_jobs"] += 1
        # Templates can predate their job. The job's own deadline is bounded by
        # the template deadline, so no actionable job depends on an erased snapshot.
        async with factory.begin() as db:
            identifiers = list(
                await db.scalars(
                    select(ImportTemplateSnapshot)
                    .where(
                        ImportTemplateSnapshot.company_id == company,
                        ImportTemplateSnapshot.expires_at <= instant,
                        ImportTemplateSnapshot.snapshot.is_not(None),
                    )
                    .order_by(ImportTemplateSnapshot.expires_at, ImportTemplateSnapshot.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for template in identifiers:
                template.snapshot = None
                evidence(db, namespace, tenant, company, template.id)
            counts["templates"] = len(identifiers)
        async with factory.begin() as db:
            remaining = (
                select(ImportJobAttempt.id)
                .join(ImportJobRevision, ImportJobAttempt.revision_id == ImportJobRevision.id)
                .where(
                    ImportJobAttempt.company_id == company, ImportJobRevision.job_id == ImportJob.id
                )
                .exists()
            )
            unvalidated = (
                select(ImportChangeSet.id)
                .join(ImportJobRevision, ImportChangeSet.revision_id == ImportJobRevision.id)
                .where(
                    ImportChangeSet.company_id == company, ImportJobRevision.job_id == ImportJob.id
                )
                .exists()
            )
            jobs = list(
                await db.scalars(
                    select(ImportJob)
                    .where(
                        ImportJob.company_id == company,
                        ImportJob.created_at < cutoff,
                        ImportJob.expires_at <= instant,
                        remaining | unvalidated,
                    )
                    .order_by(ImportJob.expires_at, ImportJob.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in jobs:
                if job.state == "IMPORTING" or pending_effects(await effects(db, job)):
                    continue
                revs = select(ImportJobRevision.id).where(
                    ImportJobRevision.company_id == company, ImportJobRevision.job_id == job.id
                )
                sets = select(ImportChangeSet.id).where(
                    ImportChangeSet.company_id == company, ImportChangeSet.revision_id.in_(revs)
                )
                records = select(ImportJobRecord.id).where(
                    ImportJobRecord.company_id == company, ImportJobRecord.change_set_id.in_(sets)
                )
                attempts = select(ImportJobAttempt.id).where(
                    ImportJobAttempt.company_id == company, ImportJobAttempt.revision_id.in_(revs)
                )
                results = select(ImportRecordResult.id).where(
                    ImportRecordResult.company_id == company,
                    ImportRecordResult.attempt_id.in_(attempts),
                )
                targets: list[tuple[type[Any], Any]] = [
                    (ImportRecordIssue, ImportRecordIssue.result_id.in_(results)),
                    (ImportRecordResult, ImportRecordResult.attempt_id.in_(attempts)),
                    (
                        ImportJobDependency,
                        ImportJobDependency.parent_id.in_(records)
                        | ImportJobDependency.child_id.in_(records),
                    ),
                    (ImportJobRecord, ImportJobRecord.change_set_id.in_(sets)),
                    (ImportChangeSet, ImportChangeSet.revision_id.in_(revs)),
                    (ImportJobAttempt, ImportJobAttempt.revision_id.in_(revs)),
                    (ImportArtifact, ImportArtifact.revision_id.in_(revs)),
                ]
                for model, condition in targets:
                    rows = await db.scalars(
                        select(model).where(model.company_id == company, condition)
                    )
                    for row in rows:
                        await db.delete(row)
                    # Flush each table in FK order; all reads and writes retain
                    # the strict session's tenant and ownership guards.
                    await db.flush()
                evidence(db, namespace, tenant, company, job.id)
                counts["history_jobs"] += 1
    return counts
