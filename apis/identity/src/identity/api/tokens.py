"""Personal tokens: secrets are returned once and cannot grant more than their owner."""

from __future__ import annotations

import datetime as dt
import secrets
import time
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7
from billing_platform.permissions import PERMISSIONS
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Company, UserApiToken
from identity.schemas.base import Page
from identity.schemas.login import ReasonRequest
from identity.schemas.tokens import TokenCreate, TokenIssued, TokenItem
from identity.services.audit import record
from identity.services.tokens import TOKEN_FORBIDDEN, token_hash

router = APIRouter(prefix="/v1", route_class=StrictRoute, responses=ERROR_RESPONSES)


@router.post("/session/api-tokens", response_model=TokenIssued, status_code=201)
async def issue_token(
    body: TokenCreate,
    request: Request,
    response: Response,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> TokenIssued:
    # Self issuance requires fresh interactive ownership proof; API tokens cannot mint tokens.
    claims = getattr(request.state, "verified_claims", None)
    if claims is None or claims.auth_time is None or not 0 <= time.time() - claims.auth_time <= 300:
        raise PermissionDeniedError("fresh interactive authentication is required")
    permissions = frozenset(body.permissions)
    if not permissions <= PERMISSIONS or permissions & TOKEN_FORBIDDEN:
        raise ValidationFailedError("unsupported API token permissions")
    target = ScopePath(company_id=body.company_id)
    for permission in permissions:
        current.require_scope(permission, target=target)
    if body.company_id is not None:
        company = await db.get(Company, body.company_id)
        if company is None or company.status != "active":
            raise ValidationFailedError("token company is unavailable")
    count = await db.scalar(
        select(func.count(UserApiToken.id)).where(
            UserApiToken.user_id == current.user_id,
            UserApiToken.revoked_at.is_(None),
            UserApiToken.expires_at > utcnow(),
        )
    )
    if count is not None and count >= 20:
        raise ConflictError("revoke an existing token before creating another")
    raw = "jpat_" + secrets.token_urlsafe(32)
    row = UserApiToken(
        id=uuid7(),
        tenant_id=current.tenant_id,
        user_id=current.user_id,
        name=body.name,
        token_prefix=raw[:12],
        token_hash=token_hash(raw),
        scopes={
            "company_id": str(body.company_id) if body.company_id else None,
            "permissions": sorted(permissions),
        },
        expires_at=utcnow() + dt.timedelta(days=body.expires_in_days),
        created_by=current.user_id,
        updated_by=current.user_id,
    )
    db.add(row)
    record(db, current, action="user.api_token_issued", entity="user_api_token", entity_id=row.id)
    await db.flush()
    response.headers["Cache-Control"] = "no-store"
    return TokenIssued(token=raw, details=TokenItem.model_validate(row))


@router.get("/session/api-tokens", response_model=Page[TokenItem])
async def tokens(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[TokenItem]:
    return await paged(
        db,
        request,
        select(UserApiToken).where(UserApiToken.user_id == current.user_id),
        model=UserApiToken,
        schema=TokenItem,
        limit=limit,
        cursor=cursor,
    )


@router.post("/api-tokens/{token_id}/revoke", response_model=TokenItem)
async def revoke_token(
    token_id: uuid.UUID,
    body: ReasonRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserApiToken:
    row = await db.get(UserApiToken, token_id)
    if row is None:
        raise NotFoundError("token not found")
    if row.user_id != current.user_id:
        current.require_scope("user.update", target=ScopePath())
    if row.revoked_at is None:
        row.revoked_at, row.revoked_by, row.updated_by = utcnow(), current.user_id, current.user_id
        record(
            db,
            current,
            action="user.api_token_revoked",
            entity="user_api_token",
            entity_id=row.id,
            reason=body.reason,
        )
    await db.flush()
    return row
