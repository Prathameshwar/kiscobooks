"""Reading and ingesting the acknowledgements that make a published policy *enforced*.

docs/catalog-warehouses.md §5. Every write here arrives from a signed source event, so there is
no ``Actor`` and no field-policy write check: the command framework's ``record`` demands
``warehouse.manage`` at company scope, which an ingestion worker cannot satisfy and must not
fake. The audit row is emitted by ``events/evidence.source_change`` instead, with no actor and
the ``system`` category (docs/audit.md §5.2).

What this module refuses to infer is the point:

* **A consumer is trusted about its own half only.** It says what it enforces; Catalog checks
  that the release, the location and the revision it names are ones Catalog actually published.
  A claim about a release Catalog never wrote is dead-lettered, never stored.
* **Absence of a clearance is never safety.** The retirement fence answers 503 *pending* when no
  trusted consumer has spoken, and it never reads a displayed zero quantity as permission.
* **Only a refusal is the caller's to fix.** A missing or stale clearance is reported as pending,
  because the consumer — not the caller — is the one who has to speak again.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.field_registry import registry
from catalog.domain.policy_release import (
    CONSUMERS,
    OPERATION_POLICY_AGGREGATE,
    RELEASE_AGGREGATE,
    RETIREMENT_AGGREGATE,
    acknowledgement_action,
    assert_clearance,
    assert_reason,
    refusal_message,
)
from catalog.domain.sources import SourceUnavailableError
from catalog.domain.warehouse_resolution import APPLIED, REJECTED, Acknowledgement
from catalog.events.evidence import source_change
from catalog.models.releases import CatalogPolicyConsumerAck, CatalogPolicyRelease
from catalog.models.warehouses import Warehouse, WarehouseOperationPolicyRevision
from catalog.schemas.acknowledgements import AcknowledgementEvent

ENTITY = "catalog.catalog_policy_consumer_ack"
#: The audited value set, taken from the field registry so a new column cannot be added to the
#: table and quietly stay out of the audit trail.
FIELDS: tuple[str, ...] = tuple(sorted(registry.get(ENTITY).fields))
#: The stock-location guard contract this fence depends on. Named in the 503 so a client can
#: match the refusal to the requirement it already sees in the readiness registry.
GUARD_SOURCE = "warehouse_stock_and_location_guards"


def claim(row: CatalogPolicyConsumerAck) -> Acknowledgement:
    """One stored row as the pure resolver's verdict."""
    return Acknowledgement(revision=row.enforced_revision, accepted=row.result == APPLIED)


async def latest_claim(
    db: AsyncSession, company: uuid.UUID, *, aggregate: str, aggregate_id: uuid.UUID, consumer: str
) -> CatalogPolicyConsumerAck | None:
    """One consumer's most recent claim about one aggregate.

    Ordered by release revision first: a claim made against a newer release supersedes an older
    one whatever revision it enforces, because it describes a later reading of the policy. One
    query per consumer, and ``CONSUMERS`` is a fixed catalogue of trusted services rather than
    client data, so the fan-out is bounded by the code (docs/api-conventions.md).
    """
    rows = await db.scalars(
        select(CatalogPolicyConsumerAck)
        .where(
            CatalogPolicyConsumerAck.company_id == company,
            CatalogPolicyConsumerAck.aggregate == aggregate,
            CatalogPolicyConsumerAck.aggregate_id == aggregate_id,
            CatalogPolicyConsumerAck.consumer == consumer,
        )
        .order_by(
            CatalogPolicyConsumerAck.release_revision.desc(),
            CatalogPolicyConsumerAck.enforced_revision.desc(),
            CatalogPolicyConsumerAck.id.desc(),
        )
        .limit(1)
    )
    return rows.first()


async def location_claims(
    db: AsyncSession, company: uuid.UUID, warehouse_id: uuid.UUID
) -> dict[str, Acknowledgement]:
    """Every trusted consumer's latest operation-policy claim about one location."""
    claims: dict[str, Acknowledgement] = {}
    for consumer in sorted(CONSUMERS):
        row = await latest_claim(
            db,
            company,
            aggregate=OPERATION_POLICY_AGGREGATE,
            aggregate_id=warehouse_id,
            consumer=consumer,
        )
        if row is not None:
            claims[consumer] = claim(row)
    return claims


async def release_rows(
    db: AsyncSession, company: uuid.UUID, release_ids: Sequence[uuid.UUID]
) -> list[CatalogPolicyConsumerAck]:
    """The release-level acknowledgements for a bounded set of releases, in one query.

    Exactly one row can exist per ``(consumer, release)`` — the schema's ``subject`` check ties a
    release claim's ``aggregate_id`` to its ``release_id``, so the uniqueness constraint bounds
    this by the two known quantities rather than by how much a consumer has said.
    """
    keys = set(release_ids)
    if not keys:
        return []
    return list(
        await db.scalars(
            select(CatalogPolicyConsumerAck)
            .where(
                CatalogPolicyConsumerAck.company_id == company,
                CatalogPolicyConsumerAck.aggregate == RELEASE_AGGREGATE,
                CatalogPolicyConsumerAck.aggregate_id.in_(keys),
            )
            .order_by(CatalogPolicyConsumerAck.release_revision, CatalogPolicyConsumerAck.id)
            .limit(len(keys) * len(CONSUMERS))
        )
    )


def by_release(
    rows: Sequence[CatalogPolicyConsumerAck],
) -> dict[uuid.UUID, list[CatalogPolicyConsumerAck]]:
    """Split release-level rows by the release each one speaks about.

    The rows themselves rather than the resolver's verdicts, because a reader that projects the
    acknowledgements needs the stored row — its consumer, its reason code, when it was made —
    and re-reading them per release would be one query per release for rows already in hand.
    """
    grouped: dict[uuid.UUID, list[CatalogPolicyConsumerAck]] = {}
    for row in rows:
        grouped.setdefault(row.aggregate_id, []).append(row)
    return grouped


def claims_of(rows: Sequence[CatalogPolicyConsumerAck]) -> dict[str, Acknowledgement]:
    """One aggregate's stored rows as the per-consumer claim map its state is resolved from.

    Exactly one row exists per ``(consumer, release)``, so keying by consumer loses nothing.
    """
    return {row.consumer: claim(row) for row in rows}


async def assert_retirable(
    db: AsyncSession,
    company: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    in_force_release: int,
    policy_revision: int,
) -> None:
    """The coordinated half of the deactivation fence (§5). Raises, or says nothing.

    Catalog's own preconditions run first, in ``tasks/warehouse_policy.py``: what this adds is
    the half Catalog does not own — stock on hand, reservations, open transfers and pending
    documents all live in Billing, and Catalog has no way to look. So it asks for a clearance,
    and the absence of one is *pending*, not permission.

    A refusal is a 409 carrying its safe reason code: the caller can act on "stock on hand".
    Everything else ``assert_clearance`` rejects — no clearance, a clearance about an older
    release, a clearance about an older operation policy — becomes a 503, because in each of
    those cases the thing that has to happen next is a consumer speaking again, and telling the
    caller to fix it would be telling them to fix something they do not control.
    """
    for consumer in sorted(CONSUMERS):
        row = await latest_claim(
            db,
            company,
            aggregate=RETIREMENT_AGGREGATE,
            aggregate_id=warehouse_id,
            consumer=consumer,
        )
        if row is None:
            raise SourceUnavailableError(
                "retiring this stock location needs a clearance from " + GUARD_SOURCE
            )
        if row.result == REJECTED:
            raise ConflictError(refusal_message(row.reason_code))
        try:
            assert_clearance(
                aggregate=row.aggregate,
                result=row.result,
                reason_code=row.reason_code,
                acknowledged_release=row.release_revision,
                in_force_release=in_force_release,
                enforced_revision=row.enforced_revision,
                policy_revision=policy_revision,
            )
        except ConflictError as exc:
            raise SourceUnavailableError(exc.message) from exc


async def verify_subject(db: AsyncSession, event: AcknowledgementEvent) -> CatalogPolicyRelease:
    """Check that everything the claim names is something Catalog actually published.

    A consumer is trusted to say what it enforces. It is not trusted about Catalog's own
    history: an ``enforced_revision`` Catalog never wrote would make every later revision read
    as applied for good, from one message.
    """
    release = await db.scalar(
        select(CatalogPolicyRelease).where(
            CatalogPolicyRelease.company_id == event.company_id,
            CatalogPolicyRelease.id == event.release_id,
        )
    )
    if release is None or release.revision != event.release_revision:
        raise ValidationFailedError("acknowledgement names a release Catalog did not publish")
    if event.aggregate == RELEASE_AGGREGATE:
        # The subject of a release-level claim is the release, and what it enforces is that
        # release's own number. Both are held in the schema too; this is the loud version.
        if event.aggregate_id != event.release_id or event.enforced_revision != release.revision:
            raise ValidationFailedError("a release acknowledgement is about its own release")
        return release
    location = await db.scalar(
        select(Warehouse.id).where(
            Warehouse.company_id == event.company_id, Warehouse.id == event.aggregate_id
        )
    )
    if location is None:
        raise ValidationFailedError("acknowledgement names a location Catalog does not hold")
    policy = await db.scalar(
        select(WarehouseOperationPolicyRevision.id).where(
            WarehouseOperationPolicyRevision.company_id == event.company_id,
            WarehouseOperationPolicyRevision.warehouse_id == event.aggregate_id,
            WarehouseOperationPolicyRevision.revision == event.enforced_revision,
        )
    )
    if policy is None:
        raise ValidationFailedError("acknowledgement names an unpublished operation policy")
    return release


def values(row: CatalogPolicyConsumerAck) -> dict[str, Any]:
    return {field: getattr(row, field) for field in FIELDS}


async def ingest(
    db: AsyncSession,
    *,
    message_id: uuid.UUID,
    consumer: str,
    event: AcknowledgementEvent,
    companies: Mapping[uuid.UUID, frozenset[uuid.UUID]],
) -> None:
    """Apply one acknowledgement, or decide it changes nothing. Idempotent by construction.

    Redelivery of the identical message never reaches here — the platform inbox dedupes on
    ``message_id`` in this transaction. What this handles is the *other* kind of repeat: a
    reordered or superseded claim, which ``acknowledgement_action`` drops rather than treating as
    a conflict, so ordinary broker behaviour cannot regress what Catalog reports as enforced.

    ``consumer`` comes from the worker's verified source key. It is a parameter rather than a
    payload field so that no code path exists by which a message could name it.
    """
    tenant = require_current_tenant()
    if consumer not in CONSUMERS:
        raise ValidationFailedError("unknown policy acknowledgement consumer")
    if event.tenant_id != tenant or event.company_id not in companies.get(tenant, frozenset()):
        raise ValidationFailedError("acknowledgement is outside the configured subscription")
    assert_reason(event.result, event.reason_code)
    await verify_subject(db, event)
    existing = await db.scalar(
        select(CatalogPolicyConsumerAck).where(
            CatalogPolicyConsumerAck.company_id == event.company_id,
            CatalogPolicyConsumerAck.consumer == consumer,
            CatalogPolicyConsumerAck.aggregate == event.aggregate,
            CatalogPolicyConsumerAck.aggregate_id == event.aggregate_id,
            CatalogPolicyConsumerAck.release_id == event.release_id,
        )
    )
    action = acknowledgement_action(
        stored_revision=None if existing is None else existing.enforced_revision,
        stored_result=None if existing is None else existing.result,
        incoming_revision=event.enforced_revision,
        incoming_result=event.result,
    )
    # NoStock is volatile state, unlike a published operation policy. Only a
    # fresh coordinated native check may restore clearance at the same policy
    # revision; broker messages retain the ordinary monotonic policy contract.
    if (
        action == "ignore"
        and existing is not None
        and event.aggregate == RETIREMENT_AGGREGATE
        and event.result == APPLIED
    ):
        from catalog.models.stock_source import (
            RETIREMENT_CHECKS,
            RetirementClearance,
            current_clearance,
        )

        checks = db.info.get(RETIREMENT_CHECKS, {})
        current = checks.get(("warehouse", event.aggregate_id))
        if (
            isinstance(current, RetirementClearance)
            and current.check_id == message_id
            and current.company_id == event.company_id
            and current.tenant_id == event.tenant_id
            and current.checked_at == event.acknowledged_at
            and current_clearance(db.sync_session, current)
            and existing.enforced_revision == event.enforced_revision
            and existing.acknowledged_at < event.acknowledged_at
        ):
            action = "apply"
    if action == "ignore":
        return
    claimed = {
        "enforced_revision": event.enforced_revision,
        "result": event.result,
        "reason_code": event.reason_code,
        "source_message_id": message_id,
        "acknowledged_at": event.acknowledged_at,
    }
    if existing is None:
        row = CatalogPolicyConsumerAck(
            id=uuid7(),
            tenant_id=tenant,
            company_id=event.company_id,
            row_version=1,
            release_id=event.release_id,
            release_revision=event.release_revision,
            consumer=consumer,
            aggregate=event.aggregate,
            aggregate_id=event.aggregate_id,
            **claimed,
        )
        db.add(row)
        await db.flush()
        after = values(row)
        source_change(
            db,
            tenant_id=tenant,
            company=event.company_id,
            entity=ENTITY,
            object_id=row.id,
            action="create",
            changed=frozenset(after),
            after=after,
        )
        return
    before = values(existing)
    if existing.row_version >= 2**31 - 1:
        raise ConflictError("acknowledgement version exhausted")
    for key, value in claimed.items():
        setattr(existing, key, value)
    existing.row_version += 1
    existing.updated_at = utcnow()
    await db.flush()
    after = values(existing)
    source_change(
        db,
        tenant_id=tenant,
        company=event.company_id,
        entity=ENTITY,
        object_id=existing.id,
        action="update",
        changed=frozenset(key for key in FIELDS if before[key] != after[key]),
        before=before,
        after=after,
    )
