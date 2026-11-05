"""Verified identity self-provisioning. No platform permissions are granted."""

from __future__ import annotations

import uuid

from billing_platform.db import tenant_scope, unfiltered
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7
from fastapi import APIRouter, Header, Request
from pydantic import Field, field_validator
from sqlalchemy import select

from identity.api.auth import Actor, refresh_current, verified_claims
from identity.api.platform import TenantProvision
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import AccountReview, AccountReviewCommand, PlatformInstallation, Tenant, User
from identity.schemas.base import StrictModel
from identity.schemas.tenant import TenantDetail
from identity.services.setup import check_administrator
from identity.services.tenant_choices import TenantChoices, choices
from identity.services.tenant_provisioning import create_tenant, resolve_defaults

router = APIRouter(prefix="/v1/onboarding", route_class=StrictRoute, responses=ERROR_RESPONSES)


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    state_code: str | None = Field(default=None, min_length=1, max_length=6)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    administrator_name: str = Field(min_length=1, max_length=100)

    @field_validator("name", "administrator_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return TenantProvision.clean_name(value)


class OnboardingStatus(StrictModel):
    linked: bool
    tenant_id: uuid.UUID | None = None
    email_verified: bool
    options: TenantChoices | None = None


@router.get("/status", response_model=OnboardingStatus)
async def status(
    request: Request, authorization: str | None = Header(default=None)
) -> OnboardingStatus:
    # Provider-authenticated self-read; a new principal has no local actor yet.
    claims = await verified_claims(request, authorization)
    async with request.app.state.session_factory() as db:
        with unfiltered():
            user = await db.scalar(select(User).where(User.authentik_sub == claims.sub))
        if user is not None:
            if claims.org_id is not None and claims.org_id != user.tenant_id:
                raise PermissionDeniedError("identity belongs to another workspace")
            with tenant_scope(user.tenant_id):
                request.state.verified_claims = claims
                await refresh_current(db, request, Actor(user.tenant_id, user.id))
        options = (
            await choices(db, request.app.state.reference_cache)
            if user is None and claims.email_verified
            else None
        )
    return OnboardingStatus(
        linked=user is not None,
        tenant_id=user.tenant_id if user else None,
        email_verified=claims.email_verified,
        options=options,
    )


@router.post("/tenant", response_model=TenantDetail, status_code=201)
async def create_workspace(
    body: WorkspaceCreate, request: Request, authorization: str | None = Header(default=None)
) -> TenantDetail:
    # Provider proof, not local authority: fixed bootstrap only for an unlinked subject.
    claims = await verified_claims(request, authorization)
    email = check_administrator(claims)
    if claims.org_id is not None:
        raise PermissionDeniedError("tenant-bound identities cannot create a workspace")
    async with request.app.state.session_factory() as db, db.begin():
        # Serialize bootstrap against installation and other self-provisioners. Subject
        # uniqueness remains the database backstop; callers cannot choose tenant/user IDs.
        installation = await db.scalar(
            select(PlatformInstallation)
            .where(PlatformInstallation.key == "platform")
            .with_for_update()
        )
        if installation is None or installation.completed_at is None:
            raise ConflictError("complete platform setup before creating a workspace")
        with tenant_scope(installation.tenant_id):
            pending = await db.scalar(
                select(AccountReviewCommand.id)
                .join(AccountReview, AccountReview.id == AccountReviewCommand.account_id)
                .where(
                    AccountReview.email == email.casefold(),
                    AccountReviewCommand.action == "approve",
                    AccountReviewCommand.status == "queued",
                )
                .limit(1)
            )
        if pending is not None:
            raise ConflictError("Your account approval is finishing. Try again shortly.")
        with unfiltered():
            user = await db.scalar(select(User).where(User.authentik_sub == claims.sub))
        if user is not None:
            with tenant_scope(user.tenant_id):
                request.state.verified_claims = claims
                await refresh_current(db, request, Actor(user.tenant_id, user.id))
                tenant = await db.get(Tenant, user.tenant_id)
                if tenant is None or user.status != "active" or tenant.status != "active":
                    raise PermissionDeniedError("workspace access is unavailable")
                # Safe replay of the same bootstrap; another workspace requires another
                # login under the documented one-login-per-tenant identity model.
                defaults = await resolve_defaults(db, body.model_dump())
                if (
                    tenant.name != body.name
                    or tenant.default_country_code != body.country_code
                    or tenant.default_state_code != body.state_code
                    or tenant.default_currency_code != defaults["currency_code"]
                    or tenant.default_timezone != defaults["timezone"]
                    or tenant.default_locale != defaults["locale"]
                    or user.display_name != body.administrator_name
                ):
                    raise ConflictError("this account already belongs to a workspace")
                return TenantDetail.model_validate(tenant)
        tenant_id, user_id = uuid7(), uuid7()
        provision = TenantProvision(**body.model_dump(), administrator_email=email)
        tenant = await create_tenant(
            db,
            provision,
            request.app.state.settings,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=user_id,
            subject=claims.sub,
        )
        return TenantDetail.model_validate(tenant)
