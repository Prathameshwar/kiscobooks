"""Atomic bounded ingestion of complete, strictly new change bundles.

Updates, tombstones, partial/replayed bundles and repeated identities use the existing
interval writer. All writes retain the normal ORM tenant, reference and evidence guards.
The final cutoff still passes independent reconciliation before becoming visible.
"""

import hashlib

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from reporting_contract.contract import FactPage, Manifest
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.core import ReportBundle, ReportGeneration
from reports.models.source_versions import ReportFactVersion, ReportSourceEpoch
from reports.tasks.common import audit
from reports.tasks.source_versions import projection


async def append_window(
    db: AsyncSession,
    generation: ReportGeneration,
    epoch: ReportSourceEpoch,
    incoming: list[tuple[Manifest, FactPage]],
) -> bool:
    if not incoming or len(incoming) > 32 or sum(len(page.items) for _, page in incoming) > 200:
        return False
    if (
        epoch.active_generation_id != generation.id
        or epoch.status != "READY"
        or generation.status != "BUILDING"
        or generation.applied_sequence != epoch.head_sequence
        or generation.target_sequence is None
    ):
        raise ConflictError("source append writer is fenced")
    keys, encoded_bytes = [], 0
    for offset, (manifest, page) in enumerate(incoming, 1):
        if (
            manifest.kind != "CHANGE"
            or manifest.sequence != epoch.head_sequence + offset
            or manifest.sequence > generation.target_sequence
            or (manifest.tenant_id, manifest.company_id) != (epoch.tenant_id, epoch.company_id)
            or (generation.tenant_id, generation.company_id) != (epoch.tenant_id, epoch.company_id)
            or (
                manifest.generation,
                manifest.schema_hash,
                manifest.scope_hash,
                manifest.permission_hash,
            )
            != (epoch.owner_generation, epoch.schema_hash, epoch.scope_hash, epoch.permission_hash)
        ):
            raise ConflictError("source append contract or sequence differs")
        if page.manifest_id != manifest.id:
            raise ConflictError("source append page identity differs")
        if page.next_after is not None or len(page.items) != manifest.fact_count:
            return False
        checksum = hashlib.sha256()
        for item in page.items:
            if item.data is None:
                return False
            encoded = canonical_json(item.model_dump(mode="json")) + b"\n"
            encoded_bytes += len(encoded)
            if encoded_bytes > 2 * 1024 * 1024:
                return False
            checksum.update(encoded)
            keys.append((item.entity, item.source_id))
        if checksum.hexdigest() != manifest.facts_hash:
            raise ConflictError("source append checksum differs")
    if len(set(keys)) != len(keys):
        return False
    if (
        await db.scalar(
            select(ReportBundle.id)
            .where(
                ReportBundle.company_id == epoch.company_id,
                ReportBundle.generation_id == generation.id,
                ReportBundle.source_id.in_([manifest.id for manifest, _ in incoming]),
            )
            .limit(1)
        )
        is not None
    ):
        return False
    if (
        keys
        and await db.scalar(
            select(ReportFactVersion.id)
            .where(
                ReportFactVersion.company_id == epoch.company_id,
                ReportFactVersion.epoch_id == epoch.id,
                tuple_(ReportFactVersion.entity, ReportFactVersion.source_id).in_(keys),
            )
            .limit(1)
        )
        is not None
    ):
        return False
    bundles = [
        ReportBundle(
            id=uuid7(),
            tenant_id=epoch.tenant_id,
            company_id=epoch.company_id,
            generation_id=generation.id,
            source_id=manifest.id,
            manifest=manifest.model_dump(mode="json"),
        )
        for manifest, _ in incoming
    ]
    db.add_all(bundles)
    await db.flush()
    for bundle, (manifest, page) in zip(bundles, incoming, strict=True):
        db.add_all(
            [
                ReportFactVersion(
                    id=uuid7(),
                    tenant_id=epoch.tenant_id,
                    company_id=epoch.company_id,
                    epoch_id=epoch.id,
                    bundle_id=bundle.id,
                    ordinal=ordinal,
                    entity=item.entity,
                    source_id=item.source_id,
                    valid_from_sequence=manifest.sequence,
                    data=item.data,
                    content_hash=item.content_hash,
                    **projection(item),
                )
                for ordinal, item in enumerate(page.items, 1)
            ]
        )
    # Flush while the guards still observe the old published head.
    await db.flush()
    for bundle, (manifest, _) in zip(bundles, incoming, strict=True):
        bundle.last_ordinal, bundle.status = manifest.fact_count, "APPLIED"
        audit(db, epoch.tenant_id, epoch.company_id, bundle.id, "ingested")
    final = incoming[-1][0]
    epoch.head_sequence, epoch.row_version = final.sequence, epoch.row_version + 1
    generation.applied_sequence = final.sequence
    generation.manifest = final.model_dump(mode="json")
    await db.flush()
    return True
