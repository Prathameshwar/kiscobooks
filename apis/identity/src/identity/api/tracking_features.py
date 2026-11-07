"""Delegated physical identity first use, with durable disable protection."""

import uuid
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    ErrorEnvelope,
    NotFoundError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.gateway import decode_actor_context, verify_retained_actor_subject
from billing_platform.ids import uuid7
from fastapi import APIRouter, Request, Response
from identity_posting.stock import TrackingReservationIntent, TrackingTerminalRequest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.posting import PostingReceipt, contract_headers, receipt
from identity.api.security import lock_tenant
from identity.api.stock_posting import authenticate, signed
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import Company, PostingReservation
from identity.services import posting
from identity.services.catalog_enrollment import is_enrolled

router = APIRouter(
    prefix="/internal/v1/tenants/{tenant_id}/companies/{company_id}/tracking/reservations",
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422)},
)
OWNER = "accounting-tracking"


def proof(
    request: Request,
    tenant: uuid.UUID,
    company: uuid.UUID,
    body: TrackingReservationIntent,
    *,
    cancellation: bool = False,
) -> None:
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    authority = body.authority
    context = verify_company_context(authority.company_context, authority.company_signature, secret)
    if cancellation:
        subject = verify_retained_actor_subject(
            authority.actor_context,
            authority.actor_signature,
            secret,
        )
        if (
            subject.tenant_id,
            subject.user_id,
            context.tenant_id,
            context.user_id,
            context.company_id,
        ) != (
            tenant,
            body.actor_user_id,
            tenant,
            body.actor_user_id,
            company,
        ) or abs(context.issued_at - subject.issued_at) > 60:
            raise AuthenticationRequiredError("tracking cancellation subject differs")
        return  # Historical subject can only seal its exact aborted operation.
    actor = decode_actor_context(authority.actor_context, authority.actor_signature, secret)
    if (actor.tenant_id, actor.user_id, context.tenant_id, context.user_id, context.company_id) != (
        tenant,
        body.actor_user_id,
        tenant,
        body.actor_user_id,
        company,
    ):
        raise AuthenticationRequiredError("tracking authority subject differs")
    context.assert_current(actor, company)
    if actor.impersonation_id or not set(body.features) <= context.features:
        raise PermissionDeniedError("tracking registration requires current company capabilities")
    actor.require_scope(
        "accounting." + body.resource.lower() + ".manage", target=ScopePath(company_id=company)
    )


def intent_hash(body: TrackingReservationIntent) -> str:
    return posting.digest(body.model_dump(mode="json", exclude={"authority"}))


async def retained(
    db: AsyncSession, company: Company, body: TrackingReservationIntent
) -> PostingReservation | None:
    row = await db.scalar(
        select(PostingReservation).where(
            PostingReservation.company_id == company.id,
            PostingReservation.operation_id == body.operation_id,
        )
    )
    if row is not None and (row.owner_service != OWNER or row.request_hash != intent_hash(body)):
        raise ConflictError("tracking operation was reused with different authority or content")
    return row


@router.post(
    "", response_model=PostingReceipt, openapi_extra=contract_headers(TrackingReservationIntent)
)
async def reserve(tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request) -> Response:
    raw, framed, secret = await authenticate(request, "tracking-reserve")
    try:
        body = TrackingReservationIntent.model_validate_json(raw)
        proof(request, tenant_id, company_id, body)
        with tenant_scope(tenant_id):
            async with request.app.state.session_factory() as db, db.begin():
                await lock_tenant(db, tenant_id)
                if not await is_enrolled(db, company_id):
                    raise PermissionDeniedError("company is not enrolled for tracking first use")
                company = await db.scalar(
                    select(Company)
                    .where(
                        Company.id == company_id,
                    )
                    .with_for_update()
                )
                if company is None:
                    raise NotFoundError("tracking company is unavailable")
                row = await retained(db, company, body)
                if row is None:
                    row = await posting.reserve(
                        db,
                        company,
                        operation_id=body.operation_id,
                        actor_user_id=body.actor_user_id,
                        expected_hash=posting.digest(await posting.configuration(db, company)),
                        features=list(body.features),
                        owner_service=OWNER,
                    )
                    row.request_hash = intent_hash(body)
                value = receipt(row)
    except (ValidationError, PlatformError) as error:
        error = (
            ValidationFailedError("invalid tracking reservation")
            if isinstance(error, ValidationError)
            else error
        )
        return signed(secret, framed, error.envelope().model_dump(mode="json"), error.status_code)
    return signed(secret, framed, value)


@router.post(
    "/{operation_id}/{outcome}",
    response_model=PostingReceipt,
    openapi_extra=contract_headers(TrackingTerminalRequest),
)
async def terminal(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    outcome: Literal["confirmed", "aborted"],
    request: Request,
) -> Response:
    raw, framed, secret = await authenticate(request, "tracking-" + outcome)
    try:
        body = TrackingTerminalRequest.model_validate_json(raw)
        if body.intent.operation_id != operation_id or (
            (outcome == "confirmed" and body.committed_at is None)
            or (outcome == "aborted" and body.committed_at is not None)
        ):
            raise ValidationFailedError("tracking terminal evidence differs from its outcome")
        with tenant_scope(tenant_id):
            async with request.app.state.session_factory() as db, db.begin():
                await lock_tenant(db, tenant_id)
                db.sync_session.info[CAPTURE_KEY] = True
                company = await db.scalar(
                    select(Company)
                    .where(
                        Company.id == company_id,
                    )
                    .with_for_update()
                )
                if company is None:
                    raise NotFoundError("tracking company is unavailable")
                row = await retained(db, company, body.intent)
                if row is None:
                    if outcome != "aborted":
                        raise NotFoundError("tracking reservation is unavailable")
                    proof(request, tenant_id, company_id, body.intent, cancellation=True)
                    # An abort arriving before a lost reserve response prevents late creation.
                    row = PostingReservation(
                        id=uuid7(),
                        tenant_id=tenant_id,
                        company_id=company_id,
                        operation_id=operation_id,
                        owner_service=OWNER,
                        actor_user_id=body.intent.actor_user_id,
                        request_hash=intent_hash(body.intent),
                        configuration_hash=posting.digest(await posting.configuration(db, company)),
                        features=list(body.intent.features),
                        status="pending",
                        created_by=body.intent.actor_user_id,
                        updated_by=body.intent.actor_user_id,
                    )
                    db.add(row)
                    await db.flush()
                await posting.terminate(
                    db,
                    company,
                    row,
                    outcome=outcome,
                    reference="accounting-tracking:" + str(operation_id),
                    posted_at=body.committed_at,
                )
                value = receipt(row)
    except (ValidationError, PlatformError) as error:
        error = (
            ValidationFailedError("invalid tracking terminal evidence")
            if isinstance(error, ValidationError)
            else error
        )
        return signed(secret, framed, error.envelope().model_dump(mode="json"), error.status_code)
    return signed(secret, framed, value)
