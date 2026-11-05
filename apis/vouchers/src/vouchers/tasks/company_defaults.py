"""Add fixed missing company types under the same fence as normal type administration."""

import uuid

from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.domain.company_defaults import FEATURES, RELEASED_VERSIONS, VERSION, catalogue
from vouchers.domain.configuration import digest, policy_wire
from vouchers.models import core as m
from vouchers.schemas.company_defaults import DefaultsResult
from vouchers.tasks.administration import write_type_revision


async def ensure_defaults(
    db: AsyncSession, company_id: uuid.UUID, features: frozenset[str], *, reconcile: bool = False
) -> DefaultsResult:
    """Trusted callers hold the company fence and verify the company/features first."""
    tenant = require_current_tenant()
    if (
        not tenant.int
        or not company_id.int
        or ("bom_definitions" in features and "inventory" not in features)
    ):
        raise ValidationFailedError("voucher defaults require valid company capabilities")
    definitions = catalogue(features)
    existing = {
        row.code: row
        for row in await db.scalars(
            select(m.VoucherType)
            .where(
                m.VoucherType.company_id == company_id,
                m.VoucherType.code.in_([row.code for row in definitions]),
            )
            .with_for_update()
        )
    }
    revisions = {
        revision.type_id: revision
        for revision in await db.scalars(
            select(m.VoucherTypeRevision)
            .join(
                m.VoucherType,
                (m.VoucherType.id == m.VoucherTypeRevision.type_id)
                & (m.VoucherType.company_id == m.VoucherTypeRevision.company_id)
                & (m.VoucherType.current_revision == m.VoucherTypeRevision.revision_number),
            )
            .where(
                m.VoucherType.company_id == company_id,
                m.VoucherType.code.in_([row.code for row in definitions]),
            )
        )
    }
    original_hashes: dict[str, set[str]] = {}
    # Discovery may precede the wizard's feature writes. Only exact, untouched system
    # recipes can follow those feature choices; an authored revision is never replaced.
    if reconcile and existing:
        for approval in (False, True):
            for currency in (False, True):
                variant = features - {"approval_workflow", "multi_currency"}
                variant |= {"approval_workflow"} if approval else set()
                variant |= {"multi_currency"} if currency else set()
                for version in RELEASED_VERSIONS:
                    for definition in catalogue(frozenset(variant), version=version):
                        original_hashes.setdefault(definition.code, set()).add(
                            digest(policy_wire(definition.policy))
                        )
    created = updated = preserved = review = 0
    for definition in definitions:
        row = existing.get(definition.code)
        if row is not None:
            # A customized policy/name remains the company's choice. Retired or
            # incompatible codes are never silently replaced, renamed or reactivated.
            if row.status != "ACTIVE" or (row.kind, row.profile) != (
                definition.kind,
                definition.profile,
            ):
                review += 1
            else:
                revision = revisions.get(row.id)
                desired = digest(policy_wire(definition.policy))
                if revision is None:
                    review += 1
                elif (
                    reconcile
                    and row.created_by is None
                    and row.updated_by is None
                    and revision.created_by is None
                    and row.name == definition.name
                    and revision.content_hash in original_hashes[definition.code]
                    and digest(revision.policy) == revision.content_hash
                    and revision.content_hash != desired
                ):
                    pending = await db.scalar(
                        select(m.VoucherOperation.id)
                        .where(
                            m.VoucherOperation.company_id == company_id,
                            m.VoucherOperation.purpose.in_(["POST", "REVERSE"]),
                            m.VoucherOperation.status == "PENDING",
                        )
                        .limit(1)
                    )
                    if pending is not None:
                        review += 1
                        continue
                    row.current_revision += 1
                    row.row_version += 1
                    await write_type_revision(db, row, definition.policy, actor_user_id=None)
                    system_audit(db, tenant, company_id, row.id, "revise")
                    updated += 1
                else:
                    preserved += 1
            continue
        row = m.VoucherType(
            id=uuid7(),
            tenant_id=tenant,
            company_id=company_id,
            code=definition.code,
            name=definition.name,
            kind=definition.kind,
            profile=definition.profile,
            status="ACTIVE",
            current_revision=1,
            created_by=None,
            updated_by=None,
        )
        db.add(row)
        await db.flush()
        await write_type_revision(db, row, definition.policy, actor_user_id=None)
        system_audit(db, tenant, company_id, row.id, "create")
        created += 1
    return DefaultsResult.model_validate(
        {
            "company_id": company_id,
            "catalogue_version": VERSION,
            "status": "NEEDS_REVIEW" if review else "READY",
            "created_count": created,
            "updated_count": updated,
            "preserved_count": preserved,
            "review_count": review,
            "features": features & FEATURES,
        }
    )


def system_audit(
    db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID, identity: uuid.UUID, action: str
) -> None:
    event = "vouchers.type." + action
    emit(
        db,
        tenant_id=tenant,
        aggregate_type="vouchers.type",
        aggregate_id=identity,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="admin",
            entity_type="vouchers.type",
            entity_id=identity,
            company_id=company,
            actor_user_id=None,
            reason=VERSION,
        )
        | {"actor_type": "system", "source_service": "vouchers"},
    )
