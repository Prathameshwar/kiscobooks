"""Local-provider routes that are not the OIDC protocol (docs/local-auth.md §4).

Two audiences, kept in two routers:

* ``internal`` — only the Auth app's server calls these (``X-Auth-Bff-Secret``). nginx never routes
  ``/identity/internal/``, so a browser cannot reach them even by guessing the path, and the secret
  stops anything else on the network. They are not in the OpenAPI client.
* ``public`` — ordinary product routes with the caller's own access token: changing your own
  password, and an administrator issuing a one-time recovery link for another user.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import time
import uuid
from typing import Any

from billing_platform.authz import ScopePath, resolve_permissions
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import assignment_target
from identity.local_auth import domain
from identity.local_auth.errors import AccountLockedError
from identity.local_auth.http import NO_STORE, local_auth, throttle, transact
from identity.local_auth.service import LocalAuth
from identity.models import PlatformInstallation, User
from identity.models.local_auth import PATH_PLATFORM
from identity.schemas.base import StrictModel
from identity.schemas.login import ReasonRequest
from identity.services import setup
from identity.services.audit import record
from identity.services.login import live_grants
from identity.services.platform_access import is_platform_operator

internal = APIRouter(
    prefix="/internal/v1/local-auth", route_class=StrictRoute, include_in_schema=False
)
public = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute)

_REQUEST_ID = Field(min_length=43, max_length=43)
_EMAIL = Field(min_length=3, max_length=320)
_SECRET = Field(min_length=1, max_length=1024)


def bff(request: Request, x_auth_bff_secret: str | None = Header(default=None)) -> LocalAuth:
    """The Auth app's server, proven by a shared secret compared in constant time."""
    service = local_auth(request)
    expected = service.settings.bff_secret.get_secret_value()
    if not x_auth_bff_secret or not domain.same(x_auth_bff_secret, expected):
        raise AuthenticationRequiredError("the caller is not authorised")
    return service


def _end_user(header: str | None) -> str | None:
    """The person's address as the Auth app reports it, or ``None`` when it did not.

    Only the Auth app can call these routes (the BFF secret), so what it reports is believed — but
    only to throttle. Without it there is deliberately *no* per-address limit: every call arrives
    from the Auth app's own address, and keying a window on that would be one budget for everyone.
    """
    if header:
        try:
            return str(ipaddress.ip_address(header.strip()))
        except ValueError:
            return None
    return None


class LoginBody(StrictModel):
    request_id: str = _REQUEST_ID
    identifier: str = Field(
        min_length=3, max_length=320, validation_alias=AliasChoices("identifier", "email")
    )
    password: str = _SECRET


class RegistrationBody(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=1, max_length=150)
    email: str = _EMAIL
    password: str = _SECRET
    country_code: str = Field(max_length=8)
    state_code: str = Field(default="", max_length=8)
    workspace_name: str | None = Field(default=None, max_length=400)


class RecoveryInspectBody(StrictModel):
    token: str = Field(min_length=1, max_length=128)


class RecoveryRedeemBody(StrictModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str = _SECRET


class AdministratorBody(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = _EMAIL
    password: str = _SECRET


def _locked(exc: AccountLockedError) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {"code": exc.code, "message": exc.message},
        "retry_after": exc.retry_after,
    }
    return JSONResponse(
        body, status_code=exc.status_code, headers={**NO_STORE, "Retry-After": str(exc.retry_after)}
    )


@internal.get("/status")
async def status(request: Request, service: LocalAuth = Depends(bff)) -> JSONResponse:
    exists = await transact(request, service.administrator_exists)
    return JSONResponse(
        {
            "provider": "local",
            "registration_enabled": service.settings.registration_enabled,
            "recovery": {"link": True, "email": False},
            "setup": {"administrator_exists": exists},
        },
        headers=NO_STORE,
    )


@internal.get("/requests/{request_id}")
async def authorization_request(
    request_id: str, request: Request, service: LocalAuth = Depends(bff)
) -> JSONResponse:
    expires = await transact(request, lambda db: service.request_expiry(db, request_id))
    return JSONResponse({"expires_at": expires.isoformat()}, headers=NO_STORE)


@internal.post("/login")
async def login(
    body: LoginBody,
    request: Request,
    service: LocalAuth = Depends(bff),
    x_client_address: str | None = Header(default=None),
) -> JSONResponse:
    address = _end_user(x_client_address)
    # Per person, per account and per sign-in request, so one attacker cannot spend another's budget
    # and one request cannot be ground on forever.
    if address is not None:
        throttle(request, "login-ip", address, 60)
    throttle(request, "login-account", domain.throttle_key(body.identifier), 10)
    throttle(request, "login-request", body.request_id, 10)
    try:
        location = await transact(
            request,
            lambda db: service.login(
                db,
                body.request_id,
                body.identifier,
                body.password,
                throttle_identity=lambda key: throttle(request, "login-identity", key, 10),
            ),
        )
    except AccountLockedError as exc:
        return _locked(exc)
    return JSONResponse({"redirect_to": location}, headers=NO_STORE)


@internal.post("/registrations", status_code=201)
async def register(
    body: RegistrationBody,
    request: Request,
    service: LocalAuth = Depends(bff),
    x_client_address: str | None = Header(default=None),
) -> JSONResponse:
    address = _end_user(x_client_address)
    if address is not None:
        throttle(request, "register-ip", address, 20)
    await transact(
        request,
        lambda db: service.register(
            db,
            name=body.name,
            username=body.username,
            email=body.email,
            password=body.password,
            country_code=body.country_code,
            state_code=body.state_code,
            workspace_name=body.workspace_name,
        ),
    )
    return JSONResponse({"status": "pending-review"}, status_code=201, headers=NO_STORE)


@internal.post("/password/recovery/inspect")
async def inspect_recovery(
    body: RecoveryInspectBody,
    request: Request,
    service: LocalAuth = Depends(bff),
    x_client_address: str | None = Header(default=None),
) -> JSONResponse:
    address = _end_user(x_client_address)
    if address is not None:
        throttle(request, "recovery-ip", address, 60)
    await transact(request, lambda db: service.inspect_recovery(db, body.token))
    return JSONResponse({"valid": True}, headers=NO_STORE)


@internal.post("/password/recovery/redeem", status_code=204)
async def redeem_recovery(
    body: RecoveryRedeemBody,
    request: Request,
    service: LocalAuth = Depends(bff),
    x_client_address: str | None = Header(default=None),
) -> Response:
    address = _end_user(x_client_address)
    if address is not None:
        throttle(request, "recovery-ip", address, 60)
    await transact(request, lambda db: service.redeem_recovery(db, body.token, body.new_password))
    return Response(status_code=204, headers=NO_STORE)


@internal.post("/setup/administrator", status_code=201)
async def setup_administrator(
    body: AdministratorBody,
    request: Request,
    service: LocalAuth = Depends(bff),
    x_setup_key: str | None = Header(default=None),
    x_client_address: str | None = Header(default=None),
) -> JSONResponse:
    settings = request.app.state.settings
    address = _end_user(x_client_address)
    if address is not None:
        throttle(request, "setup-ip", address, 20)
    setup.check_key(settings, x_setup_key)

    async def work(db: AsyncSession) -> None:
        # The installation row is the one thing every first-run step contends for; locking it makes
        # "no administrator yet, so create one" a single decision rather than a race between two
        # calls that both saw none.
        await db.scalar(
            select(PlatformInstallation.id)
            .where(PlatformInstallation.key == "platform")
            .with_for_update()
        )
        if not (await setup.status(db, settings)).available:
            raise ConflictError("Platform setup is not available.")
        if await service.administrator_exists(db):
            raise ConflictError("An administrator account already exists.")
        await service.create_administrator(
            db, name=body.name, email=body.email, password=body.password, path=PATH_PLATFORM
        )

    await transact(request, work)
    return JSONResponse({"created": True}, status_code=201, headers=NO_STORE)


# ---------------------------------------------------------------------------------- public


class PasswordChange(StrictModel):
    current_password: str = _SECRET
    new_password: str = _SECRET


class RecoveryLink(StrictModel):
    recovery_url: str
    expires_at: dt.datetime


def _provider_is_local(request: Request) -> LocalAuth:
    if request.app.state.settings.auth_provider != "local":
        raise ConflictError("Passwords are managed by the identity provider.")
    return local_auth(request)


@public.post("/v1/session/password", status_code=204)
async def change_own_password(
    body: PasswordChange, request: Request, current: Actor = Depends(actor)
) -> Response:
    service = _provider_is_local(request)
    if getattr(request.state, "api_token_id", None) is not None:
        # An API token is a credential for automation: it must not be able to guess at a password.
        raise PermissionDeniedError("interactive authentication is required")
    throttle(request, "password", str(current.user_id), 10)

    async def work(db: AsyncSession) -> None:
        user = await db.get(User, current.user_id)
        if user is None or not user.authentik_sub:
            raise ConflictError("This account has no local password.")
        await service.change_password(
            db, user.authentik_sub, body.current_password, body.new_password
        )

    try:
        with tenant_scope(current.tenant_id):
            await transact(request, work)
    except AccountLockedError as exc:
        return _locked(exc)
    return Response(status_code=204, headers=NO_STORE)


#: How recently the operator must have typed their password to issue a way into someone's account.
FRESH_SECONDS = 300


class ReauthenticationRequiredError(PermissionDeniedError):
    code = "reauthentication_required"


async def fresh_actor(request: Request, current: Actor = Depends(actor)) -> Actor:
    """The signed-in user, if their own sign-in (not a refresh of it) was in the last few minutes.

    ``auth_time`` survives a refresh unchanged, so a stolen session that keeps refreshing never
    looks fresh. Without verified claims there is nothing to measure: refused.
    """
    _provider_is_local(request)
    claims = getattr(request.state, "verified_claims", None)
    auth_time = getattr(claims, "auth_time", None)
    if auth_time is None or not 0 <= time.time() - auth_time <= FRESH_SECONDS:
        raise ReauthenticationRequiredError("sign in again to confirm this administrative action")
    return current


@public.post("/v1/users/{user_id}/password-recovery", response_model=RecoveryLink)
async def issue_recovery_link(
    user_id: uuid.UUID,
    body: ReasonRequest,
    request: Request,
    response: Response,
    current: Actor = Depends(fresh_actor),
    db: AsyncSession = Depends(session),
) -> RecoveryLink:
    current.require_scope("user.update", target=ScopePath())
    service = _provider_is_local(request)
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("user not found")
    if target.id == current.user_id:
        raise ConflictError("Use change password for your own account.")
    if target.status != "active":
        raise ConflictError("Only an active user can have a recovery link.")
    # A recovery link is a way into the account, so it is never a way to more authority than the
    # person issuing it already holds — *where* the target holds it. Each of the target's grants is
    # measured at its own scope: a clerk who posts in company A cannot reset someone who posts in
    # company B, or tenant-wide. The answer never says which permissions differ.
    # A role that starts tomorrow is authority the account already has, and the link outlives today,
    # so grants that begin later are measured too, on the day they begin.
    today = utcnow().date()
    grants, _ = await live_grants(db, target.id, include_future=True)
    for held in grants:
        if not held.permissions:
            continue
        path = await assignment_target(db, held.scope.scope_type, held.scope.scope_id)
        theirs = resolve_permissions(
            current.grants, target=path, on_date=max(today, held.valid_from)
        )
        if held.permissions - theirs:
            raise PermissionDeniedError(
                "this user holds authority you do not, so you cannot reset their password"
            )
    # The platform operator's authority is configuration, not a grant, so no comparison above can
    # see it: someone holding the same role could otherwise reset the operator and become one.
    if await is_platform_operator(db, request.app.state.settings, target):
        raise PermissionDeniedError(
            "platform administrators are recovered from the platform access page"
        )
    identity = await service.identity_for_user(db, target)
    if identity is None:
        raise ConflictError("This account does not use local sign-in.")
    token, expires = await service.issue_recovery(db, identity, issued_by=current.user_id)
    record(
        db,
        current,
        action="user.password_recovery_requested",
        entity="user",
        entity_id=target.id,
        reason=body.reason,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return RecoveryLink(recovery_url=service.recovery_url(token), expires_at=expires)
