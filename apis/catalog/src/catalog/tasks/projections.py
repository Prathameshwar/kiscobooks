"""Atomic source replacement and contiguous durable change application.

The caller owns the transaction and authenticated service scope. No network I/O
occurs here; incomplete snapshots and event gaps never make a company writable.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.claims import insert_candidate
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.snapshots import MAX_RECORDS, SnapshotRecord, paginate_records, verify_pages
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.projections import PROJECTION_MODELS, ProjectionCheckpoint, SourceEventBuffer
from catalog.schemas.identity_source import (
    CONTRACT,
    FACTS,
    CompanyScopeFact,
    CurrencyAllowanceFact,
    FeatureFact,
    IdentityChange,
    SubjectScopeFact,
    validate_facts,
)
from catalog.tasks.identity_source import (
    IdentitySourceUnavailableError,
    VerifiedSnapshot,
    validate_snapshot_scope,
)


async def lock_checkpoint(db: AsyncSession, company_id: uuid.UUID) -> ProjectionCheckpoint:
    tenant = require_current_tenant()
    if company_id == SCOPE_ALL:
        raise ValidationFailedError("projection requires a real company")
    await insert_candidate(
        db,
        ProjectionCheckpoint,
        {
            "tenant_id": tenant,
            "company_id": company_id,
            "source_key": CONTRACT,
            "source_version": 0,
            "status": "unavailable",
        },
    )
    return (
        await db.scalars(
            select(ProjectionCheckpoint)
            .where(
                ProjectionCheckpoint.company_id == company_id,
                ProjectionCheckpoint.source_key == CONTRACT,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()


def fact_values(record: SnapshotRecord) -> dict[str, Any]:
    fact = FACTS[record.kind].model_validate(record.data)
    names = {
        "company_id": "source_company_id",
        "key": "definition_key",
        "condition": "predicate_json",
    }
    return {names.get(key, key): value for key, value in fact.model_dump().items()}


def belongs(record: SnapshotRecord, company_id: uuid.UUID) -> bool:
    if record.kind == "company":
        return record.id == company_id
    fact = FACTS[record.kind].model_validate(record.data)
    if isinstance(fact, CompanyScopeFact):
        allowed = (
            {company_id}
            if isinstance(fact, FeatureFact | CurrencyAllowanceFact)
            else {SCOPE_ALL, company_id}
        )
        return fact.company_id in allowed
    if isinstance(fact, SubjectScopeFact):
        return fact.scope_type != "department" and fact.scope_id in {SCOPE_ALL, company_id}
    return True


async def activate_snapshot(db: AsyncSession, source: VerifiedSnapshot) -> ProjectionCheckpoint:
    manifest = source.manifest
    validate_snapshot_scope(
        manifest, tenant_id=require_current_tenant(), company_id=manifest.company_id
    )
    # Repeat the canonical complete-content check at the write boundary. A mutable
    # dict nested inside a frozen transport object cannot silently change a policy.
    verify_pages(manifest, paginate_records(manifest.snapshot_id, source.records))
    validate_facts(manifest, source.records)
    checkpoint = await lock_checkpoint(db, manifest.company_id)
    previous_watermark = checkpoint.source_version
    baseline = checkpoint.snapshot_source_version or 0
    if baseline > manifest.source_version:
        raise ConflictError("a newer complete Identity snapshot is already active")
    if baseline == manifest.source_version:
        if (
            checkpoint.snapshot_id != manifest.snapshot_id
            or checkpoint.snapshot_sha256 != manifest.content_sha256
        ):
            raise ConflictError("Identity snapshot generation content changed")
        await apply_buffered_changes(db, checkpoint)
        return checkpoint
    for model in PROJECTION_MODELS.values():
        rows = list(
            await db.scalars(
                select(model).where(model.company_id == manifest.company_id).limit(MAX_RECORDS + 1)
            )
        )
        if len(rows) > MAX_RECORDS:
            raise IdentitySourceUnavailableError(
                "projection replacement requires the larger job workflow"
            )
        for row in rows:
            await db.delete(row)
    await db.flush()
    for record in source.records:
        db.add(
            PROJECTION_MODELS[record.kind](
                tenant_id=manifest.tenant_id,
                company_id=manifest.company_id,
                source_id=record.id,
                source_version=manifest.source_version,
                **fact_values(record),
            )
        )
    checkpoint.source_version = manifest.source_version
    checkpoint.snapshot_source_version = manifest.source_version
    checkpoint.snapshot_id = manifest.snapshot_id
    checkpoint.snapshot_sha256 = manifest.content_sha256
    checkpoint.generated_at = manifest.generated_at
    checkpoint.expires_at = manifest.expires_at
    checkpoint.status = "ready"
    await db.flush()
    await apply_buffered_changes(db, checkpoint)
    if checkpoint.source_version < previous_watermark:
        raise ConflictError("new snapshot cannot recover already applied Identity changes")
    validate_snapshot_scope(
        manifest, tenant_id=require_current_tenant(), company_id=manifest.company_id
    )
    return checkpoint


async def buffer_change(db: AsyncSession, *, message_id: uuid.UUID, change: IdentityChange) -> None:
    tenant = require_current_tenant()
    if change.tenant_id != tenant or message_id == SCOPE_ALL:
        raise ValidationFailedError("Identity event differs from its authenticated tenant")
    payload = change.model_dump(mode="json")
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    await insert_candidate(
        db,
        SourceEventBuffer,
        {
            "tenant_id": tenant,
            "source_key": CONTRACT,
            "source_version": change.source_version,
            "previous_version": change.previous_version,
            "message_id": message_id,
            "payload_sha256": digest,
            "payload": payload,
            "generated_at": change.generated_at,
        },
    )
    existing = await db.scalar(
        select(SourceEventBuffer).where(
            SourceEventBuffer.source_key == CONTRACT,
            SourceEventBuffer.source_version == change.source_version,
        )
    )
    if existing is None or existing.payload_sha256 != digest or existing.message_id != message_id:
        raise ConflictError("Identity source message identity or generation was reused")
    checkpoints = list(
        await db.scalars(
            select(ProjectionCheckpoint)
            .where(ProjectionCheckpoint.source_key == CONTRACT)
            .order_by(ProjectionCheckpoint.id)
            .with_for_update()
            .limit(1001)
        )
    )
    if len(checkpoints) > 1000:
        raise IdentitySourceUnavailableError(
            "source delivery requires partitioned company scheduling"
        )
    for checkpoint in checkpoints:
        if checkpoint.snapshot_id is not None:
            await apply_buffered_changes(db, checkpoint)
    await prune_buffer(db, checkpoints)


async def apply_buffered_changes(db: AsyncSession, checkpoint: ProjectionCheckpoint) -> None:
    events = list(
        await db.scalars(
            select(SourceEventBuffer)
            .where(
                SourceEventBuffer.source_key == CONTRACT,
                SourceEventBuffer.source_version > checkpoint.source_version,
            )
            .order_by(SourceEventBuffer.source_version)
            .limit(1001)
        )
    )
    for event in events:
        if event.previous_version != checkpoint.source_version:
            checkpoint.status = "stale"
            await db.flush()
            return
        change = IdentityChange.model_validate(event.payload)
        if (
            hashlib.sha256(canonical_json(event.payload)).hexdigest() != event.payload_sha256
            or change.source_version != event.source_version
            or change.previous_version != event.previous_version
            or change.tenant_id != checkpoint.tenant_id
        ):
            raise ConflictError("Identity buffered event failed integrity verification")
        for record in change.records:
            model = PROJECTION_MODELS[record.kind]
            row = await db.scalar(
                select(model).where(
                    model.company_id == checkpoint.company_id, model.source_id == record.id
                )
            )
            if record.deleted or not belongs(record, checkpoint.company_id):
                if row is not None:
                    await db.delete(row)
            elif row is None:
                db.add(
                    model(
                        tenant_id=checkpoint.tenant_id,
                        company_id=checkpoint.company_id,
                        source_id=record.id,
                        source_version=change.source_version,
                        **fact_values(record),
                    )
                )
            else:
                for name, value in fact_values(record).items():
                    setattr(row, name, value)
                row.source_version = change.source_version
        checkpoint.source_version = change.source_version
        await db.flush()
    checkpoint.status = "stale" if len(events) == 1001 else "ready"
    await db.flush()


async def require_identity_context(db: AsyncSession, company_id: uuid.UUID) -> ProjectionCheckpoint:
    checkpoint = await db.scalar(
        select(ProjectionCheckpoint)
        .where(
            ProjectionCheckpoint.company_id == company_id,
            ProjectionCheckpoint.source_key == CONTRACT,
        )
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if (
        checkpoint is None
        or checkpoint.status != "ready"
        or checkpoint.snapshot_id is None
        or checkpoint.expires_at is None
        or checkpoint.expires_at <= utcnow()
    ):
        raise IdentitySourceUnavailableError("verified current Identity context is required")
    return checkpoint


async def prune_buffer(db: AsyncSession, checkpoints: list[ProjectionCheckpoint]) -> int:
    """Keep unmerged changes; obsolete capture data is disposable after a grace."""
    initialized = [row.source_version for row in checkpoints if row.snapshot_id is not None]
    query = select(SourceEventBuffer).where(
        SourceEventBuffer.source_key == CONTRACT,
        SourceEventBuffer.received_at < utcnow() - dt.timedelta(minutes=5),
    )
    if initialized:
        query = query.where(SourceEventBuffer.source_version <= min(initialized))
    rows = list(await db.scalars(query.order_by(SourceEventBuffer.source_version).limit(500)))
    for row in rows:
        await db.delete(row)
    await db.flush()
    # Hard operational bound. A larger backlog must re-bootstrap from a complete
    # snapshot; reject instead of growing an unbounded pre-bootstrap queue in SQL.
    retained = list(
        await db.scalars(
            select(SourceEventBuffer.id)
            .where(SourceEventBuffer.source_key == CONTRACT)
            .limit(10001)
        )
    )
    if len(retained) > 10000:
        raise IdentitySourceUnavailableError(
            "source capture backlog exceeds its configured workflow"
        )
    return len(rows)
