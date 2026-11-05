"""Dedicated platform boundary. Ordinary tenant roles never enable cross-tenant access."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import time
import uuid
from typing import Any, Literal
from urllib.parse import urlsplit

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.ids import uuid7
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import AwareDatetime, Field, field_validator, model_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor, refresh_current
from identity.api.listing import cursor_codec, keyset_page
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import (
    AccountReview,
    IdempotencyKey,
    RoleAssignment,
    Tenant,
    User,
    UserInvitation,
)
from identity.schemas.base import Page, PageMeta, StrictModel, looks_like_email
from identity.schemas.login import ReasonRequest
from identity.schemas.platform import PlatformDetails
from identity.schemas.platform_access import clean_text
from identity.schemas.tenant import TenantDetail, TenantUpdate
from identity.services.audit import record
from identity.services.identity_provider import administrator_directory, optional_account_directory
from identity.services.tenant_choices import TenantChoices, choices
from identity.services.tenant_provisioning import validate_defaults

router = APIRouter(prefix="/v1/platform", route_class=StrictRoute, responses=ERROR_RESPONSES)


class TenantProvision(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    state_code: str | None = Field(default=None, min_length=1, max_length=6)
    administrator_email: str = Field(min_length=3, max_length=320)
    administrator_name: str = Field(min_length=1, max_length=100)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    _email = field_validator("administrator_email")(looks_like_email)

    @field_validator("name", "administrator_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return clean_text(value)


class PlatformTenantProvision(TenantProvision):
    administrator_mode: Literal["new", "existing"] = "new"
    administrator_password: str | None = Field(default=None, min_length=12, max_length=128)
    recipient_confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def administrator_ready(self) -> PlatformTenantProvision:
        if self.administrator_mode == "new" and (
            not self.administrator_password or not self.recipient_confirmed
        ):
            raise ValueError("New administrators need a password and recipient confirmation")
        if self.administrator_mode == "existing" and self.administrator_password is not None:
            raise ValueError("Existing administrators keep their current password")
        return self


class PlatformTenantCreated(TenantDetail):
    administrator_username: str
    administrator_password: str | None = None
    administrator_mode: Literal["new", "existing"]
    sign_in_url: str
    notification_status: Literal["queued", "manual"] = "manual"


class AvailableAdministrator(StrictModel):
    email: str
    name: str
    username: str


class AdministratorAvailability(StrictModel):
    available: AvailableAdministrator | None


class PlatformTenantDetail(TenantDetail):
    suspended_at: dt.datetime | None
    suspended_reason: str | None


class PlatformInvitation(StrictModel):
    administrator_id: uuid.UUID
    invitation_id: uuid.UUID
    expires_at: dt.datetime
    url: str


class PlatformTenantItem(StrictModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class TenantStatus(ReasonRequest):
    status: Literal["active", "suspended"]
    expected_updated_at: AwareDatetime
    reason: str = Field(min_length=3, max_length=500)
    _reason = field_validator("reason", mode="before")(clean_text)


async def platform_actor(request: Request, current: Actor = Depends(actor)) -> Actor:
    claims = getattr(request.state, "verified_claims", None)
    configured = (
        claims is not None
        and request.app.state.settings.platform_operators.get(claims.sub) == current.user_id
    )
    if claims is not None and not configured:
        from identity.models.platform_installation import PlatformInstallation

        async with request.app.state.session_factory() as db:
            configured = (
                await db.scalar(
                    select(PlatformInstallation.id).where(
                        PlatformInstallation.key == "platform",
                        PlatformInstallation.completed_at.is_not(None),
                        PlatformInstallation.administrator_subject == claims.sub,
                        PlatformInstallation.administrator_id == current.user_id,
                        PlatformInstallation.tenant_id == current.tenant_id,
                    )
                )
                is not None
            )
    if claims is None or not configured:
        raise PermissionDeniedError("a configured platform operator is required")
    return current


class PlatformReauthenticationRequiredError(PermissionDeniedError):
    code = "platform_reauthentication_required"


async def fresh_platform_actor(request: Request, current: Actor = Depends(platform_actor)) -> Actor:
    claims = request.state.verified_claims
    if claims.auth_time is None or not 0 <= time.time() - claims.auth_time <= 300:
        raise PlatformReauthenticationRequiredError(
            "sign in again to confirm this administrative action"
        )
    return current


@router.get("/details", response_model=PlatformDetails)
async def platform_details(
    request: Request, current: Actor = Depends(platform_actor)
) -> PlatformDetails:
    from identity.services.platform_details import details, installation

    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await refresh_current(db, request, current)
            current.require_scope("platform.config.manage", target=ScopePath())
            return details(await installation(db))


@router.patch("/details", response_model=PlatformDetails)
async def update_platform_details(
    body: PlatformDetails, request: Request, current: Actor = Depends(fresh_platform_actor)
) -> PlatformDetails:
    from identity.services.platform_details import update

    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await refresh_current(db, request, current)
            current.require_scope("platform.config.manage", target=ScopePath())
            return await update(db, current, body)


@router.get("/tenant-options", response_model=TenantChoices)
async def tenant_options(
    request: Request, current: Actor = Depends(platform_actor)
) -> TenantChoices:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await refresh_current(db, request, current)
            current.require_scope("platform.tenant.read", target=ScopePath())
            return await choices(db, request.app.state.reference_cache)


@router.get("/tenant-administrators/available", response_model=AdministratorAvailability)
async def available_administrator(
    request: Request,
    email: str = Query(min_length=3, max_length=320),
    current: Actor = Depends(platform_actor),
) -> AdministratorAvailability:
    try:
        email = looks_like_email(email)
    except ValueError:
        raise ValidationFailedError("Enter a valid administrator email address.") from None
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await refresh_current(db, request, current)
            current.require_scope("platform.tenant.create", target=ScopePath())
            provider = administrator_directory(request)
            row = await provider.by_email(email)
            if row is None:
                return AdministratorAvailability(available=None)
            _, subject = provider.confirm(row, email)
            with unfiltered():
                linked = await db.scalar(select(User.id).where(User.authentik_sub == subject))
            if linked is not None:
                return AdministratorAvailability(available=None)
            return AdministratorAvailability(
                available=AvailableAdministrator(
                    email=email,
                    name=str(row["name"]),
                    username=str(row["username"]),
                )
            )


@router.post("/tenants", response_model=PlatformTenantCreated, status_code=201)
async def provision(
    body: PlatformTenantProvision,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    current: Actor = Depends(fresh_platform_actor),
) -> PlatformTenantCreated:
    # A one-time password may cross this request boundary, but it must never enter
    # the durable command identity or receipt. HMAC binds retries without storing it.
    settings = request.app.state.settings
    auth_url = urlsplit(settings.public_auth_url or "")
    if (
        (
            auth_url.scheme != "https"
            and not (
                auth_url.scheme == "http" and auth_url.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
        or not auth_url.hostname
        or auth_url.username
        or auth_url.password
        or auth_url.query
        or auth_url.fragment
    ):
        raise ValidationFailedError("Sign-in URL is not configured for administrator handoff.")
    canonical = body.model_dump(mode="json", exclude={"administrator_password"})
    canonical["password_proof"] = hmac.new(
        settings.actor_signing_secret.get_secret_value().encode(),
        (body.administrator_password or "").encode(),
        hashlib.sha256,
    ).hexdigest()
    command_identity = CommandIdentity(
        current.tenant_id,
        None,
        current.user_id,
        "identity.platform.tenant.provision",
        idempotency_key,
        canonical,
    )
    from identity.services.account_review import pending_email

    review_provider = optional_account_directory(request)
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as preflight, preflight.begin():
            await lock_tenant(preflight, current.tenant_id)
            await refresh_current(preflight, request, current)
            current.require_scope("platform.tenant.create", target=ScopePath())
            existing_command = await preflight.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.endpoint == command_identity.operation,
                    IdempotencyKey.key_value
                    == hashlib.sha256(idempotency_key.encode()).hexdigest(),
                )
            )
            if existing_command is not None:
                if existing_command.request_hash != command_identity.digest():
                    raise IdempotencyConflictError("idempotency key belongs to another request")
                if existing_command.expires_at <= utcnow():
                    raise ConflictError("idempotency key has expired; reconcile before retrying")
            if existing_command is None and await pending_email(
                preflight, current, review_provider, body.administrator_email
            ):
                raise ConflictError(
                    "This administrator has a pending registration. Review it first."
                )
    provider_admin = administrator_directory(request)
    marker = uuid.uuid5(uuid.NAMESPACE_URL, f"bill/tenant/{current.user_id}/{idempotency_key}")
    if body.administrator_mode == "existing":
        candidate = await provider_admin.by_email(body.administrator_email)
        if candidate is None:
            raise ConflictError("No existing sign-in account uses this email. Create one instead.")
        _, subject = provider_admin.confirm(candidate, body.administrator_email)
        administrator_username = str(candidate["username"])
    else:
        # The provider user stays inactive until the local command commits. A
        # database failure cannot leave a sign-in capable orphan at the identity provider.
        administrator_username, subject = await provider_admin.create(
            email=body.administrator_email,
            name=body.administrator_name,
            password=body.administrator_password or "",
            marker=marker,
        )

    async def authorize(db: AsyncSession, references: dict[str, Any] | None) -> None:
        await lock_tenant(db, current.tenant_id)
        await refresh_current(db, request, current)
        current.require_scope("platform.tenant.create", target=ScopePath())

    async def mutate(db: AsyncSession) -> CommandReceipt:
        from identity.services.tenant_provisioning import create_tenant

        local_pending = await db.scalar(
            select(AccountReview.id)
            .where(
                AccountReview.email == body.administrator_email.casefold(),
                AccountReview.status == "pending",
                AccountReview.provider_active.is_(False),
                AccountReview.provider_verified.is_(False),
            )
            .limit(1)
        )
        if local_pending is not None:
            raise ConflictError(
                "This administrator has a pending registration. Review it before creating a tenant."
            )
        with unfiltered():
            if await db.scalar(select(User.id).where(User.authentik_sub == subject)) is not None:
                raise ConflictError("This sign-in account already belongs to a tenant.")
        tenant_id = uuid7()
        await create_tenant(
            db,
            body,
            request.app.state.settings,
            tenant_id=tenant_id,
            user_id=uuid7(),
            actor_id=current.user_id,
            subject=subject,
        )
        record(
            db,
            current,
            action="platform.tenant_provisioned",
            entity="tenant",
            entity_id=tenant_id,
            changes={
                "status": "active",
                "administrator_mode": body.administrator_mode,
                "recipient_confirmed": body.recipient_confirmed,
            },
        )
        return CommandReceipt(
            201,
            {
                "tenant_id": str(tenant_id),
                "administrator_username": administrator_username,
                "administrator_mode": body.administrator_mode,
            },
        )

    async def render(db: AsyncSession, references: dict[str, Any]) -> PlatformTenantCreated:
        with tenant_scope(uuid.UUID(references["tenant_id"])):
            tenant = await db.get(Tenant, uuid.UUID(references["tenant_id"]))
            if tenant is None:
                raise NotFoundError("tenant not found")
            return PlatformTenantCreated.model_validate(
                {
                    **TenantDetail.model_validate(tenant).model_dump(),
                    "administrator_username": references["administrator_username"],
                    "administrator_mode": references["administrator_mode"],
                    "sign_in_url": (settings.public_auth_url or "").rstrip("/") + "/login",
                }
            )

    result = await execute_idempotent(
        request.app.state.session_factory,
        command_identity,
        authorize=authorize,
        mutate=mutate,
        render=render,
    )
    if body.administrator_mode == "new":
        await provider_admin.activate(
            email=body.administrator_email, marker=marker, subject=subject
        )
    from identity.services.onboarding_handoff import queue_ready

    tenant_id = uuid.UUID(str(result.value.id))
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as notification_db, notification_db.begin():
            await lock_tenant(notification_db, current.tenant_id)
            await refresh_current(notification_db, request, current)
            current.require_scope("platform.tenant.create", target=ScopePath())
            queued = await queue_ready(
                notification_db,
                settings,
                reference=tenant_id,
                target_tenant_id=tenant_id,
                email=body.administrator_email,
                username=administrator_username,
                locale=body.locale or "en",
            )
    return result.value.model_copy(
        update={
            "notification_status": "queued" if queued else "manual",
            "administrator_password": body.administrator_password
            if body.administrator_mode == "new" and not result.replayed
            else None,
        }
    )


@router.get("/tenants", response_model=Page[PlatformTenantItem])
async def tenants(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=100),
    status: Literal["active", "suspended", "closed"] | None = None,
    sort: str = "name",
    current: Actor = Depends(platform_actor),
) -> Page[PlatformTenantItem]:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await refresh_current(db, request, current)
            current.require_scope("platform.tenant.read", target=ScopePath())
            # Read only the lean platform tenant projection; never business entities.
            with unfiltered():
                statement = select(Tenant)
                if status is not None:
                    statement = statement.where(Tenant.status == status)
                if q is not None:
                    if len(q.strip()) < 2:
                        raise ValidationFailedError("enter at least two search characters")
                    prefix = (
                        q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                        + "%"
                    )
                    statement = statement.where(
                        or_(
                            Tenant.name.like(prefix, escape="\\"),
                            Tenant.slug.like(prefix, escape="\\"),
                        )
                    )
                rows, next_cursor, has_more = await keyset_page(
                    db,
                    statement,
                    model=Tenant,
                    projection=PlatformTenantItem,
                    page=PageRequest(limit, cursor),
                    sort=sort,
                    default="name",
                    allowed=frozenset({"name", "slug", "created_at"}),
                    codec=cursor_codec(request, "platform-tenants"),
                )
                result = Page[PlatformTenantItem](
                    items=[PlatformTenantItem.model_validate(row) for row in rows],
                    page=PageMeta(next_cursor=next_cursor, has_more=has_more),
                )
            record(
                db,
                current,
                action="platform.tenants_read",
                entity="tenant",
                entity_id=current.tenant_id,
            )
            return result


@router.get("/tenants/{tenant_id}", response_model=PlatformTenantDetail)
async def tenant_detail(
    tenant_id: uuid.UUID, request: Request, current: Actor = Depends(platform_actor)
) -> PlatformTenantDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await refresh_current(db, request, current)
            current.require_scope("platform.tenant.read", target=ScopePath())
            with tenant_scope(tenant_id):
                row = await db.get(Tenant, tenant_id)
                if row is None:
                    raise NotFoundError("tenant not found")
                record(
                    db,
                    current,
                    action="platform.tenants_read",
                    entity="tenant",
                    entity_id=tenant_id,
                )
                return PlatformTenantDetail.model_validate(row)


@router.patch("/tenants/{tenant_id}", response_model=PlatformTenantDetail)
async def update_platform_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    request: Request,
    current: Actor = Depends(fresh_platform_actor),
) -> PlatformTenantDetail:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, current.tenant_id)
            await refresh_current(db, request, current)
            current.require_scope("platform.config.manage", target=ScopePath())
            with tenant_scope(tenant_id):
                await lock_tenant(db, tenant_id)
                row = await db.get(Tenant, tenant_id)
                assert row is not None
                if row.status == "closed":
                    raise ConflictError("a closed tenant cannot be changed")
                changes = body.model_dump(exclude_unset=True)
                await validate_defaults(
                    db,
                    changes.get("default_country_code", row.default_country_code),
                    changes.get("default_currency_code", row.default_currency_code),
                    changes.get("default_timezone", row.default_timezone),
                    changes.get("default_locale", row.default_locale),
                    changes.get("default_state_code", row.default_state_code),
                )
                changed = {}
                for field, value in changes.items():
                    if getattr(row, field) != value:
                        setattr(row, field, value)
                        # Contact changes are recorded by field name only; audit contains no PII.
                        changed[field] = {"changed": True}
                if changed:
                    row.updated_by = current.user_id
                    record(
                        db,
                        Actor(tenant_id, current.user_id),
                        action="tenant.updated",
                        entity="tenant",
                        entity_id=tenant_id,
                        changes=changed,
                    )
                    record(
                        db,
                        current,
                        action="platform.tenant_updated",
                        entity="tenant",
                        entity_id=tenant_id,
                        changes=changed,
                        category="admin",
                    )
                await db.flush()
                return PlatformTenantDetail.model_validate(row)


@router.get("/tenants/{tenant_id}/administrator-invitation", response_model=PlatformInvitation)
async def administrator_invitation(
    tenant_id: uuid.UUID, request: Request, current: Actor = Depends(fresh_platform_actor)
) -> PlatformInvitation:
    from urllib.parse import urlencode

    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await refresh_current(db, request, current)
            current.require_scope("platform.tenant.create", target=ScopePath())
            with tenant_scope(tenant_id):
                tenant = await db.get(Tenant, tenant_id)
                if tenant is None:
                    raise NotFoundError("tenant not found")
                # Only a pending initial invitation, never existing tenant business users.
                invitation = await db.scalar(
                    select(UserInvitation)
                    .join(User, User.id == UserInvitation.user_id)
                    .join(RoleAssignment, RoleAssignment.subject_id == User.id)
                    .where(
                        UserInvitation.status == "pending",
                        UserInvitation.expires_at > utcnow(),
                        User.status == "invited",
                        RoleAssignment.subject_type == "user",
                        RoleAssignment.grant_reason == "initial administrator bootstrap",
                        RoleAssignment.is_active.is_(True),
                    )
                    .order_by(UserInvitation.id)
                    .limit(1)
                )
                if invitation is None:
                    raise NotFoundError("no pending administrator invitation")
                base = request.app.state.settings.public_auth_url
                if not base:
                    raise ConflictError("configure the public Auth URL")
                record(
                    db,
                    current,
                    action="platform.administrator_invitation_read",
                    entity="tenant",
                    entity_id=tenant_id,
                )
                return PlatformInvitation(
                    administrator_id=invitation.user_id,
                    invitation_id=invitation.id,
                    expires_at=invitation.expires_at,
                    url=base.rstrip("/")
                    + "/accept?"
                    + urlencode({"tenant": str(tenant_id), "invitation": str(invitation.id)}),
                )


@router.post("/tenants/{tenant_id}/lifecycle", response_model=PlatformTenantItem)
async def tenant_lifecycle(
    tenant_id: uuid.UUID,
    body: TenantStatus,
    request: Request,
    key: str = Header(alias="Idempotency-Key"),
    current: Actor = Depends(fresh_platform_actor),
) -> PlatformTenantItem:
    if tenant_id in (current.tenant_id, SCOPE_ALL):
        raise PermissionDeniedError("operators cannot suspend their own operating tenant")

    async def check(db: AsyncSession, references: dict[str, Any] | None) -> None:
        with tenant_scope(current.tenant_id):
            await lock_tenant(db, current.tenant_id)
            await refresh_current(db, request, current)
            current.require_scope("platform.tenant.suspend", target=ScopePath())
        with tenant_scope(tenant_id):
            await lock_tenant(db, tenant_id)
            row = await db.get(Tenant, tenant_id)
            if row is None:
                raise NotFoundError("tenant not found")
            if row.status == "closed":
                raise ConflictError("a closed tenant cannot be restored")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        with tenant_scope(tenant_id):
            row = await db.get(Tenant, tenant_id)
            if row is None:
                raise NotFoundError("tenant not found")
            if row.updated_at != body.expected_updated_at:
                raise ConflictError("tenant changed; refresh and review its access status")
            db.sync_session.info[CAPTURE_KEY] = True
            if row.status != body.status:
                previous_status = row.status
                row.status = body.status
                row.suspended_at = utcnow() if body.status == "suspended" else None
                row.suspended_reason = body.reason if body.status == "suspended" else None
                row.updated_by = current.user_id
                row.updated_at = utcnow()
                changes = {"status": {"from": previous_status, "to": body.status}}
                record(
                    db,
                    Actor(tenant_id, current.user_id),
                    action="tenant.lifecycle_changed",
                    entity="tenant",
                    entity_id=tenant_id,
                    reason=body.reason,
                    changes=changes,
                )
                with tenant_scope(current.tenant_id):
                    record(
                        db,
                        current,
                        action="platform.tenant_lifecycle_changed",
                        entity="tenant",
                        entity_id=tenant_id,
                        reason=body.reason,
                        changes=changes,
                    )
            await db.flush()
            return CommandReceipt(
                200, PlatformTenantItem.model_validate(row).model_dump(mode="json")
            )

    async def render(db: AsyncSession, references: dict[str, Any]) -> PlatformTenantItem:
        return PlatformTenantItem.model_validate(references)

    with tenant_scope(current.tenant_id):
        result = await execute_idempotent(
            request.app.state.session_factory,
            CommandIdentity(
                current.tenant_id,
                None,
                current.user_id,
                "identity.platform.tenant.lifecycle",
                key,
                {"tenant_id": str(tenant_id), "body": body.model_dump(mode="json")},
            ),
            authorize=check,
            mutate=mutate,
            render=render,
        )
    return result.value
