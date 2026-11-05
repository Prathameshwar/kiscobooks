"""Configured-operator account reviews; no ordinary tenant account administration."""

from __future__ import annotations

import uuid
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, refresh_current
from identity.api.listing import cursor_codec, keyset_page
from identity.api.platform import fresh_platform_actor, platform_actor
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.models import AccountReview
from identity.schemas.account_review import (
    AccountDecision,
    AccountReconciliation,
    AccountReviewDetail,
    AccountReviewItem,
)
from identity.schemas.base import Page, PageMeta, StrictModel, looks_like_email
from identity.services import account_review
from identity.services.audit import record
from identity.services.identity_provider import account_directory, optional_account_directory
from identity.services.login import live_grants
from identity.services.tenant_choices import TenantChoices, choices

router = APIRouter(
    prefix="/v1/platform/accounts",
    route_class=StrictRoute,
    responses={**ERROR_RESPONSES, 429: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)


async def _refresh_review_actor(db: AsyncSession, request: Request, current: Actor) -> None:
    """Sensitive reviews bypass the grant cache, including the post-intent check."""
    await refresh_current(db, request, current)
    current.grants, current.group_ids = await live_grants(db, current.user_id)


class AccountSyncResult(StrictModel):
    imported: int
    next_page: int | None


class PendingRegistration(StrictModel):
    id: uuid.UUID
    name: str
    email: str
    workspace_name: str | None


class PendingRegistrationResult(StrictModel):
    match: PendingRegistration | None


@router.get("/pending-registration", response_model=PendingRegistrationResult)
async def pending_registration(
    request: Request,
    email: str = Query(min_length=3, max_length=320),
    current: Actor = Depends(platform_actor),
) -> PendingRegistrationResult:
    try:
        email = looks_like_email(email.strip())
    except ValueError as exc:
        raise ValidationFailedError("Enter a valid administrator email.") from exc
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            current.require_scope("platform.tenant.create", target=ScopePath())
            provider = optional_account_directory(request)
            matches = await account_review.pending_email(db, current, provider, email)
            if len(matches) > 1:
                raise ValidationFailedError(
                    "More than one pending account uses this email. Review accounts first."
                )
            return PendingRegistrationResult(
                match=PendingRegistration.model_validate(matches[0]) if matches else None
            )


@router.get("", response_model=Page[AccountReviewItem])
async def accounts(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=100),
    status: Literal["pending", "approved", "rejected"] | None = None,
    sort: str = "-created_at",
    current: Actor = Depends(platform_actor),
) -> Page[AccountReviewItem]:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            statement = select(AccountReview)
            if status:
                statement = statement.where(AccountReview.status == status)
            if q:
                if len(q.strip()) < 2:
                    raise ValidationFailedError("Enter at least two search characters.")
                prefix = (
                    q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                )
                statement = statement.where(
                    or_(
                        AccountReview.name.like(prefix, escape="\\"),
                        AccountReview.username.like(prefix, escape="\\"),
                        AccountReview.email.like(prefix, escape="\\"),
                    )
                )
            rows, next_cursor, has_more = await keyset_page(
                db,
                statement,
                model=AccountReview,
                projection=AccountReviewItem,
                page=PageRequest(limit, cursor),
                sort=sort,
                default="-created_at",
                allowed=frozenset({"name", "username", "email", "created_at"}),
                codec=cursor_codec(request, "platform-accounts"),
            )
            record(
                db,
                current,
                action="platform.accounts_read",
                category="access",
                entity="account_review",
                entity_id=current.tenant_id,
                changes={"count": len(rows)},
            )
            return Page[AccountReviewItem](
                items=[AccountReviewItem.model_validate(row) for row in rows],
                page=PageMeta(next_cursor=next_cursor, has_more=has_more),
            )


@router.post("/sync", response_model=AccountSyncResult)
async def sync_accounts(
    request: Request, page: int = Query(1, ge=1, le=10000), current: Actor = Depends(platform_actor)
) -> AccountSyncResult:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            rows, more = await account_directory(request).page(page)
            count = await account_review.import_page(db, current, rows)
            return AccountSyncResult(imported=count, next_page=page + 1 if more else None)


@router.get("/options", response_model=TenantChoices)
async def account_options(
    request: Request, current: Actor = Depends(platform_actor)
) -> TenantChoices:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            return await choices(db, request.app.state.reference_cache)


@router.get("/{account_id}", response_model=AccountReviewDetail)
async def account(
    account_id: uuid.UUID, request: Request, current: Actor = Depends(platform_actor)
) -> AccountReviewDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            result = await account_review.detail(db, account_id, request.app.state.settings)
            record(
                db,
                current,
                action="platform.accounts_read",
                category="access",
                entity="account_review",
                entity_id=account_id,
                changes={"count": 1},
            )
            return result


@router.post("/{account_id}/reconcile", response_model=AccountReviewDetail)
async def reconcile_account(
    account_id: uuid.UUID,
    body: AccountReconciliation,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> AccountReviewDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            current.require_scope("platform.account.review", target=ScopePath())
            provider = account_directory(request)
            return await account_review.acknowledge_drift(db, current, provider, account_id, body)


@router.post("/{account_id}/review", response_model=AccountReviewDetail, status_code=202)
async def review(
    account_id: uuid.UUID,
    body: AccountDecision,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{1,128}$"),
    current: Actor = Depends(fresh_platform_actor),
) -> AccountReviewDetail:
    # Configuration must exist before accepting an intent; outages after acceptance remain durable.
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.review", target=ScopePath())
            current.require_scope("platform.account.read", target=ScopePath())
            provider = account_directory(request)
            command = await account_review.decide(db, current, account_id, body, idempotency_key)
            command_id = command.id
        # Intent/audit has committed before native I/O; every replay still rechecks authority.
        from identity.models import AccountReviewCommand

        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await _refresh_review_actor(db, request, current)
            current.require_scope("platform.account.read", target=ScopePath())
            current.require_scope("platform.account.review", target=ScopePath())
            saved = await db.get(AccountReviewCommand, command_id)
            if saved is not None:
                await account_review.reconcile(
                    db, current, provider, saved, request.app.state.settings
                )
            return await account_review.detail(db, account_id, request.app.state.settings)
