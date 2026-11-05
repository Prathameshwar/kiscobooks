"""Create immutable source snapshots from locked authoritative Identity tables."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7
from billing_platform.snapshots import (
    MAX_RECORDS,
    SnapshotManifest,
    SnapshotPage,
    SnapshotRecord,
    manifest_digest,
    paginate_records,
)
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.events.catalog_source import (
    CONTRACT,
    SOURCE_SPECS,
    _wire,
    lock_generation,
    source_outbox,
)
from identity.models import Company
from identity.models.catalog_source import CatalogSourcePage, CatalogSourceSnapshot


async def load_snapshot(
    db: AsyncSession, company_id: uuid.UUID, snapshot_id: uuid.UUID
) -> CatalogSourceSnapshot:
    row = await db.scalar(
        select(CatalogSourceSnapshot).where(CatalogSourceSnapshot.id == snapshot_id)
    )
    if row is None:
        raise NotFoundError("source snapshot is unavailable")
    if row.company_id != company_id:
        raise PermissionDeniedError("source snapshot belongs to another company")
    if row.expires_at <= utcnow():
        raise ConflictError("source snapshot expired; request a new snapshot identity")
    verified_manifest(row)
    return row


def verified_manifest(row: CatalogSourceSnapshot) -> SnapshotManifest:
    try:
        result = SnapshotManifest.model_validate(row.manifest)
    except ValidationError as exc:
        raise ConflictError("source snapshot failed integrity verification") from exc
    if (
        result.contract != CONTRACT
        or result.snapshot_id != row.id
        or result.tenant_id != row.tenant_id
        or result.company_id != row.company_id
        or result.source_version != row.source_version
        or result.generated_at != row.generated_at
        or result.expires_at != row.expires_at
        or set(result.stream_counts) != set(SOURCE_SPECS)
    ):
        raise ConflictError("source snapshot failed integrity verification")
    return result


async def create_snapshot(
    db: AsyncSession, *, company_id: uuid.UUID, request_id: uuid.UUID, ttl_seconds: int
) -> SnapshotManifest:
    tenant = require_current_tenant()
    if company_id == SCOPE_ALL or request_id == SCOPE_ALL or not 15 <= ttl_seconds <= 300:
        raise ValidationFailedError("invalid source snapshot scope or lifetime")
    # The same lock precedes participating native writes, including deletes.
    version = await db.run_sync(lambda sync: lock_generation(sync, tenant))
    # A no-change barrier fills this generation in the event stream. Consumers can
    # detect every gap, including snapshots requested by another company.
    db.add(source_outbox(tenant, version, []))
    existing = await db.scalar(
        select(CatalogSourceSnapshot).where(
            CatalogSourceSnapshot.company_id == company_id,
            CatalogSourceSnapshot.request_id == request_id,
        )
    )
    if existing is not None:
        await load_snapshot(db, company_id, existing.id)
        return verified_manifest(existing)
    await prune_expired_snapshots(db, company_id=company_id)
    active = list(
        await db.scalars(
            select(CatalogSourceSnapshot.id)
            .where(
                CatalogSourceSnapshot.company_id == company_id,
                CatalogSourceSnapshot.expires_at > utcnow(),
            )
            .limit(32)
        )
    )
    if len(active) >= 32:
        raise ConflictError("too many live source snapshots; reuse an existing snapshot")
    company = await db.scalar(select(Company.id).where(Company.id == company_id))
    if company is None:
        raise NotFoundError("company is unavailable")
    records: list[SnapshotRecord] = []
    counts: dict[str, int] = {}
    for kind, spec in SOURCE_SPECS.items():
        model = spec.model
        columns = [model.id, *(getattr(model, field) for field in spec.fields)]
        query = select(*columns).order_by(model.id).limit(MAX_RECORDS + 1)
        if spec.scope == "company_identity":
            query = query.where(model.id == company_id)
        elif spec.scope == "company":
            query = query.where(model.company_id == company_id)
        elif spec.scope == "definition":
            query = query.where(
                model.company_id.in_((SCOPE_ALL, company_id)),
                model.entity_type.startswith("catalog.", autoescape=True),
            )
        elif spec.scope in {"policy", "assignment"}:
            query = query.where(
                or_(
                    (model.scope_type == "tenant") & (model.scope_id == SCOPE_ALL),
                    (model.scope_type == "company") & (model.scope_id == company_id),
                )
            )
            if spec.scope == "policy":
                query = query.where(model.entity_type.startswith("catalog.", autoescape=True))
        rows = (await db.execute(query)).mappings().all()
        counts[kind] = len(rows)
        if len(records) + len(rows) > MAX_RECORDS:
            raise ValidationFailedError("source snapshot requires the larger job workflow")
        records.extend(
            SnapshotRecord(
                kind=kind, id=row["id"], data={key: _wire(row[key]) for key in spec.fields}
            )
            for row in rows
        )
    snapshot_id = uuid7()
    pages = paginate_records(snapshot_id, records)
    digests = tuple(page.digest() for page in pages)
    now = utcnow()
    manifest = SnapshotManifest(
        contract=CONTRACT,
        snapshot_id=snapshot_id,
        tenant_id=tenant,
        company_id=company_id,
        source_version=version,
        generated_at=now,
        expires_at=now + dt.timedelta(seconds=ttl_seconds),
        record_count=len(records),
        page_sha256=digests,
        content_sha256=manifest_digest(digests),
        stream_counts=counts,
    )
    db.add(
        CatalogSourceSnapshot(
            id=snapshot_id,
            tenant_id=tenant,
            company_id=company_id,
            request_id=request_id,
            source_version=version,
            generated_at=now,
            expires_at=manifest.expires_at,
            manifest=manifest.model_dump(mode="json"),
        )
    )
    await db.flush()
    db.add_all(
        [
            CatalogSourcePage(
                tenant_id=tenant,
                company_id=company_id,
                snapshot_id=snapshot_id,
                page_number=page.page_number,
                content_sha256=page.digest(),
                payload=page.model_dump(mode="json"),
            )
            for page in pages
        ]
    )
    await db.flush()
    return manifest


async def read_page(
    db: AsyncSession, *, company_id: uuid.UUID, snapshot_id: uuid.UUID, page_number: int
) -> SnapshotPage:
    snapshot = await load_snapshot(db, company_id, snapshot_id)
    row = await db.scalar(
        select(CatalogSourcePage).where(
            CatalogSourcePage.company_id == company_id,
            CatalogSourcePage.snapshot_id == snapshot_id,
            CatalogSourcePage.page_number == page_number,
        )
    )
    if row is None:
        raise NotFoundError("source snapshot page is unavailable")
    try:
        result = SnapshotPage.model_validate(row.payload)
    except ValidationError as exc:
        raise ConflictError("source snapshot failed integrity verification") from exc
    manifest = verified_manifest(snapshot)
    if (
        result.snapshot_id != snapshot_id
        or result.page_number != page_number
        or result.digest() != row.content_sha256
        or page_number >= len(manifest.page_sha256)
        or result.digest() != manifest.page_sha256[page_number]
    ):
        raise ConflictError("source snapshot failed integrity verification")
    return result


async def prune_expired_snapshots(db: AsyncSession, *, company_id: uuid.UUID) -> int:
    """Bounded disposable-cache retention; leases plus a five-minute retry grace."""
    rows = list(
        await db.scalars(
            select(CatalogSourceSnapshot)
            .where(
                CatalogSourceSnapshot.company_id == company_id,
                CatalogSourceSnapshot.expires_at < utcnow() - dt.timedelta(minutes=5),
            )
            .order_by(CatalogSourceSnapshot.expires_at, CatalogSourceSnapshot.id)
            .limit(5)
        )
    )
    for row in rows:
        pages = list(
            await db.scalars(
                select(CatalogSourcePage)
                .where(
                    CatalogSourcePage.company_id == company_id,
                    CatalogSourcePage.snapshot_id == row.id,
                )
                .limit(MAX_RECORDS + 1)
            )
        )
        if len(pages) > MAX_RECORDS:
            raise ConflictError("source artifact exceeds bounded retention workflow")
        for page in pages:
            await db.delete(page)
        await db.flush()
        await db.delete(row)
    await db.flush()
    return len(rows)
