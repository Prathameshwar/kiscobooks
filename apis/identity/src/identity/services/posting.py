"""Company configuration reservation policy. No money transaction calls this synchronously."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.features import FEATURES
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from identity_posting.stock import StockReservationSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.domain.company_immutability import IMMUTABLE_AFTER_POSTING, changed_fields
from identity.models import Company, CompanyFeature, PostingReservation, User
from identity.services.audit import record


async def configuration(db: AsyncSession, company: Company) -> dict[str, Any]:
    values = {
        key: (value.isoformat() if isinstance(value, dt.date) else value)
        for key in sorted(IMMUTABLE_AFTER_POSTING)
        for value in [getattr(company, key)]
    }
    features = sorted(
        await db.scalars(
            select(CompanyFeature.feature_key).where(
                CompanyFeature.company_id == company.id, CompanyFeature.is_enabled.is_(True)
            )
        )
    )
    return {"settings": values, "enabled_features": features}


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def source_values(source: StockReservationSource | None) -> dict[str, Any]:
    return {
        "authority_kind": "STOCK" if source else "GENERAL",
        "source_execution_id": source.execution_id if source else None,
        "source_command_hash": source.command_hash if source else None,
        "source_action": source.action if source else None,
    }


def reservation_hash(
    actor: uuid.UUID,
    configuration_hash: str,
    features: list[str],
    source: StockReservationSource | None,
) -> str:
    values: dict[str, Any] = {
        "actor_user_id": str(actor),
        "configuration_hash": configuration_hash,
        "features": sorted(set(features)),
    }
    if source:
        values["stock_source"] = source.model_dump(mode="json")
    return digest(values)


async def guard_edit(db: AsyncSession, company: Company, incoming: dict[str, Any]) -> None:
    before = {key: getattr(company, key) for key in incoming}
    if not changed_fields(before, incoming) & IMMUTABLE_AFTER_POSTING:
        return
    if (
        await db.scalar(
            select(PostingReservation.id)
            .where(
                PostingReservation.company_id == company.id, PostingReservation.status == "pending"
            )
            .limit(1)
        )
        is not None
    ):
        raise ConflictError("company settings are frozen by an unresolved posting reservation")


async def guard_disable(db: AsyncSession, company_id: uuid.UUID, feature: str) -> None:
    pending = list(
        await db.scalars(
            select(PostingReservation.features)
            .where(
                PostingReservation.company_id == company_id, PostingReservation.status == "pending"
            )
            .limit(101)
        )
    )
    if len(pending) > 100 or any(feature in keys for keys in pending):
        raise ConflictError("feature is frozen by an unresolved posting reservation")


async def reserve(
    db: AsyncSession,
    company: Company,
    *,
    operation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    expected_hash: str,
    features: list[str],
    owner_service: str = "billing",
    stock_source: StockReservationSource | None = None,
) -> PostingReservation:
    if owner_service not in {"billing", "accounting", "accounting-tracking"}:
        raise ValidationFailedError("unsupported posting owner")
    if owner_service == "accounting-tracking" and (
        stock_source is not None
        or not set(features) <= {"batch_tracking", "expiry_tracking", "serial_tracking"}
        or not features
    ):
        raise ValidationFailedError(
            "tracking registration reserves physical identity features only"
        )
    request_hash = reservation_hash(actor_user_id, expected_hash, features, stock_source)
    existing = await db.scalar(
        select(PostingReservation).where(
            PostingReservation.company_id == company.id,
            PostingReservation.operation_id == operation_id,
        )
    )
    if existing is not None:
        if existing.owner_service != owner_service:
            raise ConflictError("posting operation belongs to another service")
        if existing.request_hash != request_hash:
            raise ConflictError("posting operation was reused with different parameters")
        if any(
            getattr(existing, key) != value for key, value in source_values(stock_source).items()
        ):
            raise ConflictError("posting authority differs from its retained source")
        return existing
    if company.status != "active":
        raise ConflictError("company is not active")
    actor = await db.get(User, actor_user_id)
    if actor is None or actor.status != "active":
        raise ValidationFailedError("posting actor is not active in this tenant")
    state = await configuration(db, company)
    if digest(state) != expected_hash:
        raise ConflictError("company configuration changed; recalculate before reserving")
    if not set(features) <= FEATURES.keys() or not set(features) <= set(state["enabled_features"]):
        raise ValidationFailedError("posting requires an unavailable feature")
    required = set(features)
    for feature in list(features):
        required.update(FEATURES[feature].requires)
    # Freeze all transitive prerequisites so they cannot change underneath first use.
    while any(set(FEATURES[key].requires) - required for key in tuple(required)):
        required.update(dep for key in tuple(required) for dep in FEATURES[key].requires)
    if not required <= set(state["enabled_features"]):
        raise ValidationFailedError("posting feature prerequisites are unavailable")
    pending = list(
        await db.scalars(
            select(PostingReservation.id)
            .where(
                PostingReservation.company_id == company.id, PostingReservation.status == "pending"
            )
            .limit(100)
        )
    )
    if len(pending) >= 100:
        raise ConflictError("reconcile pending posting reservations before continuing")
    row = PostingReservation(
        id=uuid7(),
        tenant_id=company.tenant_id,
        company_id=company.id,
        operation_id=operation_id,
        owner_service=owner_service,
        actor_user_id=actor_user_id,
        request_hash=request_hash,
        configuration_hash=expected_hash,
        features=sorted(required),
        status="pending",
        created_by=actor_user_id,
        updated_by=actor_user_id,
        **source_values(stock_source),
    )
    db.add(row)
    record(
        db,
        Actor(company.tenant_id, actor_user_id),
        action="company.posting_reserved",
        entity="posting_reservation",
        entity_id=row.id,
        company_id=company.id,
    )
    await db.flush()
    return row


async def terminate(
    db: AsyncSession,
    company: Company,
    row: PostingReservation,
    *,
    outcome: str,
    reference: str,
    posted_at: dt.datetime | None,
) -> None:
    if row.status != "pending":
        if (
            row.status != outcome
            or row.terminal_reference != reference
            or (outcome == "confirmed" and row.confirmed_at != posted_at)
        ):
            raise ConflictError("posting reservation already has a different terminal outcome")
        return
    now = utcnow()
    if outcome == "confirmed":
        if (
            posted_at is None
            or posted_at.tzinfo is None
            or posted_at > now + dt.timedelta(seconds=30)
            or posted_at < row.created_at - dt.timedelta(seconds=1)
        ):
            raise ValidationFailedError(
                "confirmation requires the actual bounded posting timestamp"
            )
        row.confirmed_at = posted_at
        if company.first_posted_at is None and row.owner_service != "accounting-tracking":
            company.first_posted_at = posted_at
            company.updated_by = row.actor_user_id
        features = await db.scalars(
            select(CompanyFeature).where(
                CompanyFeature.company_id == company.id,
                CompanyFeature.feature_key.in_(row.features),
            )
        )
        for feature in features:
            if row.owner_service == "accounting-tracking" and feature.feature_key == "inventory":
                continue  # Empty physical identities do not constitute stock movement.
            if FEATURES[feature.feature_key].locks_on is not None and feature.locked_at is None:
                feature.locked_at = posted_at
                feature.updated_by = row.actor_user_id
    elif outcome == "aborted":
        row.aborted_at = now
    else:
        raise ValidationFailedError("invalid posting outcome")
    row.status, row.terminal_reference, row.updated_by = outcome, reference, row.actor_user_id
    action = "company.posting_confirmed" if outcome == "confirmed" else "company.posting_aborted"
    record(
        db,
        Actor(company.tenant_id, row.actor_user_id),
        action=action,
        entity="posting_reservation",
        entity_id=row.id,
        company_id=company.id,
    )
    emit(
        db,
        tenant_id=company.tenant_id,
        aggregate_type="posting_reservation",
        aggregate_id=row.id,
        event_type="identity.posting_reservation.terminal",
        payload={
            "operation_id": str(row.operation_id),
            "company_id": str(company.id),
            "status": outcome,
            "configuration_hash": row.configuration_hash,
            "confirmed_at": posted_at.isoformat() if posted_at else None,
            "features": row.features,
        },
    )
    await db.flush()


async def retain_abort(
    db: AsyncSession,
    company: Company,
    *,
    operation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    expected_hash: str,
    features: list[str],
    owner_service: str,
    stock_source: StockReservationSource | None = None,
) -> PostingReservation:
    """Retain a canceled intent even if configuration changed before the first reserve.

    Only the authenticated terminal-abort route calls this, under the tenant lock. The
    caller terminates in the same transaction: this row can never grant posting authority.
    Late reserve requests see the retained abort and cannot resurrect the operation.
    """
    request_hash = reservation_hash(actor_user_id, expected_hash, features, stock_source)
    existing = await db.scalar(
        select(PostingReservation).where(
            PostingReservation.company_id == company.id,
            PostingReservation.operation_id == operation_id,
        )
    )
    if existing is not None:
        if existing.owner_service != owner_service or existing.request_hash != request_hash:
            raise ConflictError("canceled posting identity differs from its reservation")
        if any(
            getattr(existing, key) != value for key, value in source_values(stock_source).items()
        ):
            raise ConflictError("canceled posting authority differs from its retained source")
        return existing
    # The actor may have been deactivated since preparing. Tenant ownership still applies.
    if await db.get(User, actor_user_id) is None:
        raise ValidationFailedError("posting actor does not belong to this tenant")
    row = PostingReservation(
        id=uuid7(),
        tenant_id=company.tenant_id,
        company_id=company.id,
        operation_id=operation_id,
        owner_service=owner_service,
        actor_user_id=actor_user_id,
        request_hash=request_hash,
        configuration_hash=expected_hash,
        features=sorted(set(features)),
        status="pending",
        created_by=actor_user_id,
        updated_by=actor_user_id,
        **source_values(stock_source),
    )
    db.add(row)
    await db.flush()
    return row
