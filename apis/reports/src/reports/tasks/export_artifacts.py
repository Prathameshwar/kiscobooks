"""Scoped artifact creation/publication and conservative temporary-only cleanup."""

import uuid
from dataclasses import asdict
from pathlib import Path
from typing import cast

from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.config import Settings
from reports.domain.reporting.contracts import ExportDefinition, Format
from reports.models.export_artifacts import ReportExportArtifact
from reports.models.framework import ReportJob
from reports.rendering.identity import implementation
from reports.storage.filesystem import LocalArtifactStore, StoredObject
from reports.tasks import framework_jobs as jobs
from reports.tasks.common import audit, get


def definition(format_name: str, settings: Settings) -> ExportDefinition:
    media = {
        "CSV": "text/csv",
        "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "HTML": "text/html; charset=utf-8",
        "PDF": "application/pdf",
    }
    if format_name not in media:
        raise ConflictError("requested export renderer is unavailable")
    if format_name in {"HTML", "PDF"}:
        from reports.rendering.presentation import renderer_identity

        return ExportDefinition(
            cast(Format, format_name),
            media[format_name],
            renderer_identity(),
            "presentation-v1",
            "noto-local-v1",
            min(settings.export_max_rows, 5000 if format_name == "PDF" else 20000),
            200000,
            min(settings.export_max_bytes, 64 * 1024 * 1024),
            min(settings.export_timeout_seconds, 60),
            "frozen-display-with-exact-source-v1",
            200 if format_name == "PDF" else None,
        )
    return ExportDefinition(
        cast(Format, format_name),
        media[format_name],
        "tabular-v1:" + implementation(),
        "tabular-v1",
        "none",
        settings.export_max_rows,
        settings.export_max_rows * 200,
        settings.export_max_bytes,
        settings.export_timeout_seconds,
        "exact-decimal-text-above-15-digits-v1",
    )


def store(settings: Settings) -> LocalArtifactStore:
    if settings.artifact_root is None:
        raise ConflictError("private persistent report storage is not configured")
    return LocalArtifactStore(Path(settings.artifact_root))


async def begin(
    db: AsyncSession, job: ReportJob, renderer: ExportDefinition
) -> ReportExportArtifact:
    owned = await jobs.owned(db, job.company_id, job.id, job.attempt)
    if owned.kind != "EXPORT" or owned.parent_id is None:
        raise ConflictError("only export attempts can create private artifacts")
    identity = uuid7()
    artifact = ReportExportArtifact(
        id=identity,
        tenant_id=job.tenant_id,
        company_id=job.company_id,
        job_id=job.id,
        run_id=owned.parent_id,
        attempt=job.attempt,
        state="STAGING",
        storage_key=identity.hex,
        media_type="application/zip"
        if job.parameters.get("delivery") == "PACKAGE"
        else renderer.media_type,
        filename=f"report-{job.parent_id}."
        + ("zip" if job.parameters.get("delivery") == "PACKAGE" else renderer.format.lower()),
        renderer=asdict(renderer),
        created_by=job.actor_id,
    )
    db.add(artifact)
    await db.flush()
    audit(db, job.tenant_id, job.company_id, artifact.id, "artifact_staged", job.actor_id)
    return artifact


async def publish(
    db: AsyncSession, job: ReportJob, identity: uuid.UUID, output: StoredObject, count: int
) -> None:
    owned = await jobs.owned(db, job.company_id, job.id, job.attempt)
    artifact = await get(db, job.company_id, ReportExportArtifact, identity, lock=True)
    if (
        artifact.job_id != job.id
        or artifact.attempt != job.attempt
        or artifact.storage_key != output.key
    ):
        raise ConflictError("artifact publication belongs to a different attempt")
    artifact.state, artifact.content_hash = "PUBLISHED", output.content_hash
    artifact.byte_count, artifact.row_count = output.byte_count, count
    artifact.row_version += 1
    await db.flush()  # Validate against the still-owned RUNNING attempt before terminal completion.
    owned.completed_rows = count
    await db.flush()  # The next locked lookup refreshes state from durable SQL values.
    await jobs.complete(
        db,
        job.company_id,
        job.id,
        job.attempt,
        {
            "artifact_id": str(identity),
            "row_count": count,
            "content_hash": output.content_hash,
            "byte_count": output.byte_count,
            "format": artifact.renderer["format"],
            "media_type": artifact.media_type,
            "delivery": job.parameters.get("delivery", "SINGLE"),
            "renderer": artifact.renderer,
        },
    )
    audit(db, job.tenant_id, job.company_id, identity, "artifact_published", job.actor_id)


async def cleanup_candidate(
    db: AsyncSession, company: uuid.UUID, identity: uuid.UUID
) -> str | None:
    """Only a proven obsolete attempt is removable; never infer abandonment from file age."""
    artifact = await get(db, company, ReportExportArtifact, identity)
    job = await get(db, company, ReportJob, artifact.job_id, lock=True)
    if job.attempt == artifact.attempt and job.status in {"QUEUED", "RUNNING"}:
        return None
    # Even an expired RUNNING lease can have an alive process. Wait for a fenced newer
    # attempt or terminal job. Completed durable objects are deliberately never removed.
    return artifact.storage_key


async def candidates(
    db: AsyncSession, company: uuid.UUID, after: uuid.UUID | None
) -> list[ReportExportArtifact]:
    query = select(ReportExportArtifact).where(ReportExportArtifact.company_id == company)
    query = query.where(ReportExportArtifact.temporary_cleaned_at.is_(None))
    if after is not None:
        query = query.where(ReportExportArtifact.id > after)
    return list(await db.scalars(query.order_by(ReportExportArtifact.id).limit(100)))
