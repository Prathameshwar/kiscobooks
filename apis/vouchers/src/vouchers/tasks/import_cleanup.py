"""Bounded owner-scoped retention; effects and business vouchers are never removed."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.import_cleanup import evidence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from vouchers.models import imports as m


async def sweep(
    db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID, *, limit: int, now: dt.datetime
) -> dict[str, int]:
    if not 1 <= limit <= 100 or tenant.int == 0 or company.int == 0:
        raise ValueError("cleanup requires a bounded company scope")
    counts = {"payload_jobs": 0, "templates": 0, "history_jobs": 0}
    previous = db.info.get("import_cleanup")
    db.info["import_cleanup"] = True
    try:
        payload = (
            select(m.VoucherImportArtifact.id)
            .where(
                m.VoucherImportArtifact.company_id == company,
                m.VoucherImportArtifact.job_id == m.VoucherImportJob.id,
                m.VoucherImportArtifact.byte_count > 0,
            )
            .exists()
        )
        jobs = list(
            await db.scalars(
                select(m.VoucherImportJob)
                .where(
                    m.VoucherImportJob.company_id == company,
                    m.VoucherImportJob.expires_at <= now,
                    payload,
                )
                .order_by(m.VoucherImportJob.expires_at, m.VoucherImportJob.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            if job.state in {"STAGED", "VALIDATING", "READY", "COMMITTING"}:
                job.state = "EXPIRED"
            job.selection_digest = None
            job.row_version += 1
            for artifact in await db.scalars(
                select(m.VoucherImportArtifact).where(
                    m.VoucherImportArtifact.company_id == company,
                    m.VoucherImportArtifact.job_id == job.id,
                )
            ):
                artifact.content, artifact.byte_count = b"", 0
                artifact.row_version += 1
            for revision in await db.scalars(
                select(m.VoucherImportRevision)
                .where(
                    m.VoucherImportRevision.company_id == company,
                    m.VoucherImportRevision.job_id == job.id,
                )
                .options(
                    load_only(
                        m.VoucherImportRevision.id,
                        m.VoucherImportRevision.tenant_id,
                        m.VoucherImportRevision.company_id,
                    )
                )
            ):
                revision.snapshot, revision.content = None, None
            for row in await db.scalars(
                select(m.VoucherImportRow)
                .where(
                    m.VoucherImportRow.company_id == company, m.VoucherImportRow.job_id == job.id
                )
                .options(
                    load_only(
                        m.VoucherImportRow.id,
                        m.VoucherImportRow.tenant_id,
                        m.VoucherImportRow.company_id,
                        m.VoucherImportRow.state,
                        m.VoucherImportRow.row_version,
                    )
                )
            ):
                row.source_input, row.prepared_input = {"header": {}, "lines": []}, None
                if row.state in {"STAGED", "VALID", "WARNING"}:
                    row.state = "NOT_SELECTED"
                row.row_version += 1
            job.valid_count = job.warning_count = 0
            for attempt in await db.scalars(
                select(m.VoucherImportAttempt).where(
                    m.VoucherImportAttempt.company_id == company,
                    m.VoucherImportAttempt.job_id == job.id,
                    m.VoucherImportAttempt.outcome == "RUNNING",
                )
            ):
                attempt.outcome, attempt.finished_at = "EXPIRED", now
            evidence(db, "vouchers", tenant, company, job.id)
            counts["payload_jobs"] += 1
        templates = list(
            await db.scalars(
                select(m.ImportTemplateSnapshot)
                .where(
                    m.ImportTemplateSnapshot.company_id == company,
                    m.ImportTemplateSnapshot.expires_at <= now,
                    m.ImportTemplateSnapshot.snapshot.is_not(None),
                )
                .order_by(m.ImportTemplateSnapshot.expires_at, m.ImportTemplateSnapshot.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for template in templates:
            template.snapshot = None
            evidence(db, "vouchers", tenant, company, template.id)
            counts["templates"] += 1
        await db.flush()
        old_rows = (
            select(m.VoucherImportRow.id)
            .where(
                m.VoucherImportRow.company_id == company,
                m.VoucherImportRow.job_id == m.VoucherImportJob.id,
            )
            .exists()
        )
        old = list(
            await db.scalars(
                select(m.VoucherImportJob)
                .where(
                    m.VoucherImportJob.company_id == company,
                    m.VoucherImportJob.created_at < now - dt.timedelta(days=365),
                    m.VoucherImportJob.expires_at <= now,
                    old_rows,
                )
                .order_by(m.VoucherImportJob.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in old:
            attempts = select(m.VoucherImportAttempt.id).where(
                m.VoucherImportAttempt.company_id == company,
                m.VoucherImportAttempt.job_id == job.id,
            )
            targets: list[tuple[Any, Any]] = [
                (m.VoucherImportResult, m.VoucherImportResult.attempt_id.in_(attempts)),
                (m.VoucherImportAttempt, m.VoucherImportAttempt.job_id == job.id),
                (m.VoucherImportRow, m.VoucherImportRow.job_id == job.id),
                (m.VoucherImportArtifact, m.VoucherImportArtifact.job_id == job.id),
            ]
            for model, condition in targets:
                for row in await db.scalars(
                    select(model)
                    .where(model.company_id == company, condition)
                    .options(load_only(model.id, model.tenant_id, model.company_id))
                ):
                    await db.delete(row)
                await db.flush()
            evidence(db, "vouchers", tenant, company, job.id)
            counts["history_jobs"] += 1
        await db.flush()
    finally:
        if previous is None:
            db.info.pop("import_cleanup", None)
        else:
            db.info["import_cleanup"] = previous
    return counts


async def cleanup_imports(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    namespace: str = "vouchers",
    *,
    limit: int = 50,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    if namespace != "vouchers":
        raise ValueError("incorrect import owner")
    with tenant_scope(tenant):
        async with factory.begin() as db:
            return await sweep(db, tenant, company, limit=limit, now=now or utcnow())


if __name__ == "__main__":
    from billing_platform.import_cleanup_cli import main

    main("vouchers", cleanup_imports)
