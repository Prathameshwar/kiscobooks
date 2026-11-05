"""Global catalog: configured platform operators only, fresh authentication for writes."""

import uuid
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, refresh_current
from identity.api.listing import paged
from identity.api.platform import fresh_platform_actor, platform_actor
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.models.platform_price import PlatformPrice, PlatformPriceRevision
from identity.schemas.base import Page
from identity.schemas.platform_price import (
    Category,
    PlatformPriceDetail,
    PlatformPriceInput,
    PlatformPriceItem,
    PlatformPriceLifecycle,
    PlatformPriceRevisionItem,
    PlatformPriceUpdate,
)
from identity.services.audit import record
from identity.services.platform_details import installation
from identity.services.platform_pricing import apply, check_version, detail, snapshot, unique_code

router = APIRouter(
    prefix="/v1/platform/pricing", route_class=StrictRoute, responses=ERROR_RESPONSES
)


async def authorize(
    db: AsyncSession, request: Request, current: Actor, *, write: bool = False
) -> None:
    # One global installation lock serializes code creation and catalog writes across operators.
    if write:
        await lock_tenant(db, current.tenant_id)
        await installation(db, lock=True)
    await refresh_current(db, request, current)
    current.require_scope("platform.config.manage", target=ScopePath())


@router.get("", response_model=Page[PlatformPriceItem])
async def list_prices(
    request: Request,
    current: Actor = Depends(platform_actor),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    category: Category | None = None,
    status: Literal["active", "inactive", "deleted", "all"] = "active",
    q: str | None = Query(None, min_length=2, max_length=100),
) -> Page[PlatformPriceItem]:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            statement = select(PlatformPrice)
            if status != "all":
                statement = statement.where(
                    PlatformPrice.deleted_at.is_not(None)
                    if status == "deleted"
                    else PlatformPrice.deleted_at.is_(None)
                )
                if status != "deleted":
                    statement = statement.where(PlatformPrice.is_active == (status == "active"))
            if category:
                statement = statement.where(PlatformPrice.category == category)
            if q:
                statement = statement.where(
                    PlatformPrice.code.startswith(q.strip(), autoescape=True)
                )
            return await paged(
                db,
                request,
                statement,
                model=PlatformPrice,
                schema=PlatformPriceItem,
                limit=limit,
                cursor=cursor,
            )


@router.get("/{price_id}", response_model=PlatformPriceDetail)
async def get_price(
    price_id: uuid.UUID, request: Request, current: Actor = Depends(platform_actor)
) -> PlatformPriceDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            row = await db.get(PlatformPrice, price_id)
            if row is None:
                raise NotFoundError("pricing offering not found")
            return detail(row)


@router.get("/{price_id}/revisions", response_model=Page[PlatformPriceRevisionItem])
async def revisions(
    price_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(platform_actor),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> Page[PlatformPriceRevisionItem]:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            if await db.get(PlatformPrice, price_id) is None:
                raise NotFoundError("pricing offering not found")
            return await paged(
                db,
                request,
                select(PlatformPriceRevision).where(PlatformPriceRevision.price_id == price_id),
                model=PlatformPriceRevision,
                schema=PlatformPriceRevisionItem,
                limit=limit,
                cursor=cursor,
            )


@router.post("", response_model=PlatformPriceDetail, status_code=201)
async def create_price(
    body: PlatformPriceInput, request: Request, current: Actor = Depends(fresh_platform_actor)
) -> PlatformPriceDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await authorize(db, request, current, write=True)
            await unique_code(db, body.code)
            row = PlatformPrice(
                **body.model_dump(),
                version=1,
                created_by=current.user_id,
                updated_by=current.user_id,
            )
            if not body.is_active:
                row.deactivated_at, row.deactivated_by = utcnow(), current.user_id
            db.add(row)
            await db.flush()
            snapshot(db, row, current)
            record(
                db,
                current,
                action="platform.price_created",
                entity="platform_price",
                entity_id=row.id,
                changes={"version": 1},
            )
            return detail(row)


@router.patch("/{price_id}", response_model=PlatformPriceDetail)
async def update_price(
    price_id: uuid.UUID,
    body: PlatformPriceUpdate,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> PlatformPriceDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await authorize(db, request, current, write=True)
            row = check_version(
                await db.get(PlatformPrice, price_id, with_for_update=True), body.expected_version
            )
            return await apply(
                db,
                row,
                PlatformPriceInput.model_validate(body.model_dump(exclude={"expected_version"})),
                current,
            )


@router.post("/{price_id}/{action}", response_model=PlatformPriceDetail)
async def lifecycle(
    price_id: uuid.UUID,
    action: Literal["delete", "restore"],
    body: PlatformPriceLifecycle,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> PlatformPriceDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await authorize(db, request, current, write=True)
            row = check_version(
                await db.get(PlatformPrice, price_id, with_for_update=True), body.expected_version
            )
            if (action == "delete") == (row.deleted_at is not None):
                raise ConflictError("this offering is already in the requested state")
            row.deleted_at = utcnow() if action == "delete" else None
            row.is_active = False
            row.deactivated_at, row.deactivated_by = utcnow(), current.user_id
            row.updated_by, row.version = current.user_id, row.version + 1
            snapshot(db, row, current)
            record(
                db,
                current,
                action="platform.price_deleted"
                if action == "delete"
                else "platform.price_restored",
                entity="platform_price",
                entity_id=row.id,
                changes={"version": row.version},
            )
            return detail(row)
