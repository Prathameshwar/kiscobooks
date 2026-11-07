"""Prepare first-use protection outside the local physical-identity transaction."""

import hashlib
import uuid

from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import IdempotencyKey, Outbox
from billing_platform.errors import (
    ConflictError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandIdentity, CommandResult, has_retained_command
from billing_platform.outbox import emit
from fastapi import Request
from identity_posting import ReservationError, ReservationRejectedError
from identity_posting.stock import StockAuthority, TrackingReservationIntent, tracking_root
from pydantic import BaseModel
from sqlalchemy import select

from accounting.api.auth import Access
from accounting.models.masters import AccountingSetup
from accounting.models.stock_tracking import StockLot
from accounting.resources import Resource
from accounting.schemas.stock_tracking import (
    BatchCorrect,
    BatchPrepare,
    ExpectedVersion,
    SerialPrepare,
    TrackingSource,
)
from accounting.stock_resources import BATCH, SERIAL
from accounting.tasks.access import authorize
from accounting.tasks.stock_tracking import Action, assert_feature, command, command_identity


class TrackingProtectionUnavailableError(PlatformError):
    status_code = 503
    code = "tracking_protection_unavailable"


async def abort(
    request: Request, current: Access, intent: TrackingReservationIntent, identity: CommandIdentity
) -> None:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory.begin() as db:
            # Serialize the terminal decision with native tracking mutation. A
            # committed receipt wins; an abort marker prevents a late mutation.
            await db.scalar(
                select(AccountingSetup.id)
                .where(
                    AccountingSetup.company_id == current.context.company_id,
                )
                .with_for_update()
            )
            committed = await db.scalar(
                select(IdempotencyKey.request_hash).where(
                    IdempotencyKey.endpoint == identity.operation,
                    IdempotencyKey.key_value == hashlib.sha256(identity.key.encode()).hexdigest(),
                    IdempotencyKey.state == "completed",
                )
            )
            if committed == identity.digest():
                return
            if await db.scalar(
                select(Outbox.id)
                .where(
                    Outbox.aggregate_id == intent.operation_id,
                    Outbox.event_type == "accounting.tracking_feature.abort",
                )
                .limit(1)
            ):
                return
            emit(
                db,
                tenant_id=current.actor.tenant_id,
                aggregate_type="tracking_reservation",
                aggregate_id=intent.operation_id,
                event_type="accounting.tracking_feature.abort",
                payload={
                    "company_id": str(current.context.company_id),
                    "intent": intent.model_dump(mode="json"),
                    "committed_at": None,
                },
            )


async def protected_command(
    request: Request,
    current: Access,
    spec: Resource,
    body: BatchCorrect | BatchPrepare | ExpectedVersion | SerialPrepare,
    key: str,
    action: Action,
    object_id: uuid.UUID | None = None,
    source: TrackingSource | None = None,
) -> CommandResult[BaseModel]:
    identity = command_identity(current, spec, body, key, action, object_id)
    factory = request.app.state.session_factory
    authorize(current, spec, "read")
    authorize(current, spec, "manage")
    if action == "prepare":
        assert_feature(current, spec)
    if await has_retained_command(factory, identity):
        return await command(factory, current, spec, body, key, action, object_id, source)
    features = {"batch_tracking" if spec is BATCH else "serial_tracking"}
    if getattr(body, "expires_on", None) is not None:
        features.add("expiry_tracking")
    if spec is BATCH and action == "correct" and "expires_on" not in body.model_fields_set:
        with tenant_scope(current.actor.tenant_id):
            async with factory() as db:
                expires = await db.scalar(
                    select(StockLot.expires_on).where(
                        StockLot.company_id == current.context.company_id,
                        StockLot.id == object_id,
                    )
                )
                if expires is not None:
                    features.add("expiry_tracking")
    if spec is SERIAL and source and source.lot_tracking:
        features.add("batch_tracking")
        with tenant_scope(current.actor.tenant_id):
            async with factory() as db:
                expires = await db.scalar(
                    select(StockLot.expires_on).where(
                        StockLot.company_id == current.context.company_id,
                        StockLot.id == getattr(body, "lot_id", None),
                    )
                )
                if expires is not None:
                    features.add("expiry_tracking")
    if "expiry_tracking" in features and "expiry_tracking" not in current.context.features:
        raise ValidationFailedError(
            "Enable expiry tracking before entering expiry dates",
            fields={"expires_on": "Enable expiry tracking or remove the optional expiry date"},
        )
    intent = TrackingReservationIntent(
        operation_id=uuid.uuid5(
            current.context.company_id,
            identity.operation + ":" + str(current.actor.user_id) + ":" + key,
        ),
        actor_user_id=current.actor.user_id,
        command_hash=identity.digest(),
        resource="BATCH" if spec is BATCH else "SERIAL",
        features=tuple(sorted(features)),
        authority=StockAuthority(
            actor_context=request.headers["x-actor-context"],
            actor_signature=request.headers["x-actor-signature"],
            company_context=request.headers["x-company-context"],
            company_signature=request.headers["x-company-signature"],
        ),
    )
    client = request.app.state.tracking_feature_client
    if client is None:
        raise ConflictError("Tracking first-use protection is not configured")
    try:
        receipt = await client.request(
            tracking_root(current.actor.tenant_id, current.context.company_id),
            "tracking-reserve",
            intent,
        )
        if (
            receipt.operation_id != intent.operation_id
            or receipt.status != "pending"
            or (
                not set(intent.features) <= set(receipt.features)
                or not set(receipt.features)
                <= {"inventory", "batch_tracking", "serial_tracking", "expiry_tracking"}
            )
        ):
            raise ConflictError("Tracking reservation is unavailable or has a different outcome")
    except ReservationRejectedError as error:
        if error.status_code in {401, 403}:
            raise PermissionDeniedError("Tracking first-use authorization was rejected") from error
        if error.status_code == 422:
            raise ValidationFailedError(
                "Tracking first-use capabilities are unavailable"
            ) from error
        raise ConflictError("Tracking first-use reservation was rejected") from error
    except ReservationError as error:
        # A lost response can still have reserved successfully. Leave that exact
        # operation pending so retry can safely recover it, never change its key.
        raise TrackingProtectionUnavailableError(
            "Tracking first-use protection could not be verified; retry the same request"
        ) from error
    try:
        return await command(
            factory, current, spec, body, key, action, object_id, source, tracking_intent=intent
        )
    except PlatformError as error:
        if isinstance(error, ConflictError) and error.message in {
            "request is busy; retry with the same idempotency key",
            "request is already in progress; retry later",
        }:
            raise  # A transient local wait must leave the exact reservation retryable.
        if not await has_retained_command(factory, identity):
            await abort(request, current, intent, identity)
        raise
