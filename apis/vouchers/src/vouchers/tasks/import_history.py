"""Voucher adapter for shared revision/attempt evidence; the native job stays canonical."""

import uuid
from typing import cast

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.models import imports as m
from vouchers.tasks import imports as run

MAX_REVISIONS = 20
MAX_ATTEMPTS = 100


async def revision(
    db: AsyncSession, current: Access, job: m.VoucherImportJob
) -> m.VoucherImportRevision:
    row = await db.scalar(
        select(m.VoucherImportRevision).where(
            m.VoucherImportRevision.company_id == job.company_id,
            m.VoucherImportRevision.job_id == job.id,
            m.VoucherImportRevision.revision == job.revision,
        )
    )
    if row is None:
        # Upgrade compatibility: capture legacy staged data before its first new attempt.
        artifact = await db.scalar(
            select(m.VoucherImportArtifact).where(
                m.VoucherImportArtifact.company_id == job.company_id,
                m.VoucherImportArtifact.job_id == job.id,
            )
        )
        raw = None
        if artifact is not None and artifact.byte_count:
            await db.refresh(artifact, ["content"])
            raw = artifact.content
        row = await capture_revision(db, current, job, raw)
    return row


async def capture_revision(
    db: AsyncSession,
    current: Access,
    job: m.VoucherImportJob,
    raw: bytes | None,
    template_id: uuid.UUID | None = None,
) -> m.VoucherImportRevision:
    rows = await run.job_rows(db, current, job.id)
    row = run.new(
        m.VoucherImportRevision,
        current,
        job_id=job.id,
        revision=job.revision,
        template_id=template_id,
        source_format=job.source_format,
        source_sha256=job.input_sha256,
        content=raw,
        snapshot={
            "rows": [
                {
                    "key": r.import_key,
                    "ordinal": r.ordinal,
                    "source": r.source_input,
                    "positions": r.source_rows,
                }
                for r in rows
            ]
        },
        expires_at=job.expires_at,
    )
    db.add(row)
    await db.flush()
    return row


async def active(db: AsyncSession, job: m.VoucherImportJob) -> m.VoucherImportAttempt | None:
    return cast(
        m.VoucherImportAttempt | None,
        await db.scalar(
            select(m.VoucherImportAttempt)
            .where(
                m.VoucherImportAttempt.company_id == job.company_id,
                m.VoucherImportAttempt.job_id == job.id,
                m.VoucherImportAttempt.outcome == "RUNNING",
            )
            .order_by(m.VoucherImportAttempt.id.desc())
            .limit(1)
        ),
    )


async def begin(db: AsyncSession, current: Access, job: m.VoucherImportJob, phase: str) -> None:
    if await active(db, job) is not None:
        raise ConflictError("an import attempt is already running")
    attempts = await db.scalar(
        select(func.count(m.VoucherImportAttempt.id)).where(
            m.VoucherImportAttempt.company_id == job.company_id,
            m.VoucherImportAttempt.job_id == job.id,
        )
    )
    if (attempts or 0) >= MAX_ATTEMPTS:
        raise ConflictError("import attempt limit reached; upload remaining vouchers as a new job")
    source = await revision(db, current, job)
    db.add(
        run.new(
            m.VoucherImportAttempt,
            current,
            job_id=job.id,
            revision_id=source.id,
            phase=phase,
            outcome="RUNNING",
        )
    )
    await db.flush()


async def checkpoint(
    db: AsyncSession,
    current: Access,
    job: m.VoucherImportJob,
    rows: list[m.VoucherImportRow],
    *,
    finish: bool = False,
) -> None:
    attempt = await active(db, job)
    if attempt is None:
        # A job started before deployment is journaled as it resumes.
        await begin(db, current, job, "COMMIT" if job.state == "COMMITTING" else "VALIDATE")
        attempt = await active(db, job)
        assert attempt is not None
    existing = set(
        await db.scalars(
            select(m.VoucherImportResult.record_key).where(
                m.VoucherImportResult.company_id == job.company_id,
                m.VoucherImportResult.attempt_id == attempt.id,
            )
        )
    )
    for row in rows:
        row.error_count = len(row.errors)
        if row.import_key in existing or row.state == "STAGED":
            continue
        if attempt.phase == "COMMIT" and row.state in {"VALID", "WARNING"}:
            continue
        value = run.row_view(row, detail=True, owner=False, hide=False)
        value = {key: str(v) if isinstance(v, uuid.UUID) else v for key, v in value.items()}
        db.add(
            run.new(
                m.VoucherImportResult,
                current,
                attempt_id=attempt.id,
                record_key=row.import_key,
                ordinal=row.ordinal,
                result=value,
            )
        )
    if finish:
        attempt.outcome, attempt.finished_at = job.state, utcnow()
    await db.flush()


async def close(db: AsyncSession, current: Access, job: m.VoucherImportJob) -> None:
    if await active(db, job) is not None:
        await checkpoint(db, current, job, await run.job_rows(db, current, job.id), finish=True)
