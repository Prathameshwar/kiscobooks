from __future__ import annotations

from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.reference_management import ReferenceRevision
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.pagination import PageRequest
from billing_platform.reference.contracts import CatalogData
from fastapi import APIRouter, Depends, Query, Request
from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, refresh_current
from identity.api.listing import cursor_codec, keyset_page
from identity.api.platform import fresh_platform_actor, platform_actor
from identity.api.reference_route import ReferenceRoute
from identity.api.route import ERROR_RESPONSES
from identity.api.security import lock_tenant
from identity.domain.india_states import gst_state_codes
from identity.models import PlatformInstallation, Timezone
from identity.schemas.base import Page, PageMeta
from identity.schemas.reference import TimezoneChoice
from identity.schemas.reference_management import (
    KINDS,
    ReferenceDetail,
    ReferenceItem,
    ReferenceKind,
    ReferenceLifecycle,
    ReferenceOptions,
    ReferenceUpdate,
)
from identity.services import reference_management as service
from identity.services.company_choices import options as reference_options

router = APIRouter(
    prefix="/v1/platform/references",
    route_class=ReferenceRoute,
    responses=ERROR_RESPONSES,
    tags=["Platform reference management"],
)


async def authorize(
    db: AsyncSession, request: Request, current: Actor, *, write: bool = False
) -> None:
    if write:
        if not request.state.verified_claims.email_verified:
            raise PermissionDeniedError("a verified email is required for reference changes")
        await lock_tenant(db, current.tenant_id)
        # One owner lock orders committed UUIDv7 journal entries across all kinds.
        await db.scalar(
            select(PlatformInstallation)
            .where(PlatformInstallation.key == "platform")
            .with_for_update()
        )
    await refresh_current(db, request, current)
    if write:
        from identity.services.login import live_grants

        current.grants, current.group_ids = await live_grants(db, current.user_id)
    current.require_scope("platform.config.manage", target=ScopePath())


@router.get("/options", response_model=ReferenceOptions)
async def options(request: Request, current: Actor = Depends(platform_actor)) -> ReferenceOptions:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            return await reference_options(db, request.app.state.reference_cache)


@router.get("/timezones", response_model=Page[TimezoneChoice])
async def timezone_listing(
    request: Request,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    status: Literal["active", "archived"] | None = None,
    sort: str = "code",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=3000),
    current: Actor = Depends(platform_actor),
) -> Page[TimezoneChoice]:
    """Read-only pinned IANA catalogue; administrators cannot edit timezone rules."""
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            statement = select(Timezone)
            if status:
                statement = statement.where(Timezone.is_active.is_(status == "active"))
            if q:
                term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                statement = statement.where(
                    or_(
                        Timezone.name.like(term, escape="\\"), Timezone.code.like(term, escape="\\")
                    )
                )
            rows, next_cursor, more = await keyset_page(
                db,
                statement,
                model=Timezone,
                page=PageRequest(limit, cursor),
                sort=sort,
                allowed=frozenset({"name", "code"}),
                default="code",
                codec=cursor_codec(request, "reference.timezones"),
                projection=TimezoneChoice,
                identity_field="code",
            )
            return Page[TimezoneChoice](
                items=[TimezoneChoice.model_validate(row) for row in rows],
                page=PageMeta(next_cursor=next_cursor, has_more=more),
            )


@router.get("/{kind}", response_model=Page[ReferenceItem])
async def listing(
    kind: ReferenceKind,
    request: Request,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    status: Literal["active", "archived"] | None = None,
    country_code: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    sort: str = "name",
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=3000),
    current: Actor = Depends(platform_actor),
) -> Page[ReferenceItem]:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            statement = select(ReferenceRevision).where(ReferenceRevision.kind == KINDS[kind])
            if country_code:
                if kind != "states":
                    raise ValidationFailedError("country filter is only valid for states")
                statement = statement.where(ReferenceRevision.parent_code == country_code)
            if status:
                statement = statement.where(ReferenceRevision.is_active.is_(status == "active"))
            if q:
                term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                statement = statement.where(
                    or_(
                        ReferenceRevision.name.like(term, escape="\\"),
                        ReferenceRevision.code.like(term, escape="\\"),
                        (ReferenceRevision.kind == "state")
                        & ReferenceRevision.code.in_(
                            [
                                code
                                for code, gst in gst_state_codes().items()
                                if gst.startswith(q.strip())
                            ]
                            if kind == "states"
                            else []
                        ),
                    )
                )
            rows, next_cursor, more = await keyset_page(
                db,
                statement,
                model=ReferenceRevision,
                page=PageRequest(limit, cursor),
                sort=sort,
                allowed=frozenset({"name", "code"}),
                default="name",
                codec=cursor_codec(request, "reference." + kind),
                projection=ReferenceItem,
                identity_field="code",
            )
            return Page[ReferenceItem](
                items=[ReferenceItem.model_validate(row) for row in rows],
                page=PageMeta(next_cursor=next_cursor, has_more=more),
            )


@router.get("/{kind}/{code}", response_model=ReferenceDetail)
async def get(
    kind: ReferenceKind, code: str, request: Request, current: Actor = Depends(platform_actor)
) -> ReferenceDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            return await service.detail(db, await service.load(db, KINDS[kind], code))


@router.post("/{kind}", response_model=ReferenceDetail, status_code=201)
async def create(
    kind: ReferenceKind,
    body: CatalogData,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> ReferenceDetail:
    if body.kind != KINDS[kind] or not body.is_active:
        raise ValidationFailedError("invalid new reference kind or state")
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await authorize(db, request, current, write=True)
            return await service.detail(db, await service.persist(db, current, body))


@router.patch("/{kind}/{code}", response_model=ReferenceDetail)
async def edit(
    kind: ReferenceKind,
    code: str,
    body: ReferenceUpdate,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> ReferenceDetail:
    if body.data.kind != KINDS[kind] or body.data.code != code:
        raise ValidationFailedError("reference code and kind cannot be changed")
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await authorize(db, request, current, write=True)
            row = await service.load(db, KINDS[kind], code)
            if row.version != body.version:
                raise ConflictError("this record changed; reload before saving")
            if body.data.is_active != row.is_active:
                raise ValidationFailedError(
                    "use the archive or restore action to change availability"
                )
            return await service.detail(
                db, await service.persist(db, current, body.data, current=row, action="updated")
            )


@router.post("/{kind}/{code}/{action}", response_model=ReferenceDetail)
async def lifecycle(
    kind: ReferenceKind,
    code: str,
    action: Literal["archive", "restore"],
    body: ReferenceLifecycle,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> ReferenceDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await authorize(db, request, current, write=True)
            row = await service.load(db, KINDS[kind], code)
            if row.version != body.version:
                raise ConflictError("this record changed; reload before continuing")
            active = action == "restore"
            if row.is_active == active:
                return await service.detail(db, row)
            if not active:
                await service.archive_allowed(db, row)
            data: CatalogData = TypeAdapter(CatalogData).validate_python(
                {"kind": row.kind, **row.payload, "is_active": active}
            )
            return await service.detail(
                db,
                await service.persist(
                    db,
                    current,
                    data,
                    current=row,
                    reason=body.reason,
                    action="restored" if active else "archived",
                ),
            )
