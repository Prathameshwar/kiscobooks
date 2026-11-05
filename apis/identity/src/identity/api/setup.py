"""First-run boundary: setup key replaces an existing operator only before completion."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from sqlalchemy import select, text

from identity.api.auth import verified_claims
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.schemas.setup import (
    SetupAdministrator,
    SetupCheck,
    SetupChecks,
    SetupChoice,
    SetupRequest,
    SetupResult,
    SetupStatus,
)
from identity.services import setup
from identity.services.tenant_choices import choices

router = APIRouter(prefix="/v1/setup", route_class=StrictRoute, responses=ERROR_RESPONSES)


@router.get("/status", response_model=SetupStatus)
async def status(request: Request) -> SetupStatus:
    # Explicitly public: only availability/completion flags, never installation configuration.
    async with request.app.state.session_factory() as db:
        return await setup.status(db, request.app.state.settings)


@router.get("/checks", response_model=SetupChecks)
async def checks(request: Request, x_setup_key: str | None = Header(default=None)) -> SetupChecks:
    from billing_platform.constants import SCOPE_ALL
    from billing_platform.db import unfiltered

    from identity.models import Role

    setup.check_key(request.app.state.settings, x_setup_key)
    checks = []
    countries: list[SetupChoice] = []
    currencies: list[SetupChoice] = []
    languages: list[SetupChoice] = []
    timezones: list[SetupChoice] = []
    try:
        async with request.app.state.session_factory() as db:
            await db.execute(text("SELECT 1"))
            available = await setup.status(db, request.app.state.settings)
            catalogue = await choices(db, request.app.state.reference_cache)
            countries = [
                SetupChoice.model_validate(item.model_dump()) for item in catalogue.countries
            ]
            currencies = [
                SetupChoice.model_validate(item.model_dump()) for item in catalogue.currencies
            ]
            languages = [
                SetupChoice.model_validate(item.model_dump()) for item in catalogue.languages
            ]
            timezones = [
                SetupChoice.model_validate(item.model_dump()) for item in catalogue.timezones
            ]
            with unfiltered():
                role = await db.scalar(
                    select(Role.id).where(
                        Role.tenant_id == SCOPE_ALL,
                        Role.key == "platform_admin",
                        Role.is_active.is_(True),
                    )
                )
            ready = (
                available.available
                and all((countries, currencies, languages, timezones))
                and role is not None
            )
        checks.append(
            SetupCheck(
                name="Identity database and defaults",
                status="ready" if ready else "failed",
                message="Ready"
                if ready
                else "Run Identity installation, or setup is already closed.",
            )
        )
    except Exception:
        # Database/driver exceptions can contain credentials or SQL; return a fixed message.
        checks.append(
            SetupCheck(
                name="Identity database and defaults",
                status="failed",
                message="Database unavailable. Check server configuration and migrations.",
            )
        )
    try:
        redis = request.app.state.redis
        if redis is None or not await redis.ping():
            raise RuntimeError("Redis unavailable")
        checks.append(SetupCheck(name="Redis", status="ready", message="Connected"))
    except Exception:
        checks.append(
            SetupCheck(
                name="Redis",
                status="failed",
                message="Configure IDENTITY_REDIS_URL and start Redis.",
            )
        )
    if request.app.state.settings.auth_provider == "local":
        name, ready_message = "Identity signing keys", "Published by Identity"
        failed_message = (
            "Check IDENTITY_LOCAL_AUTH and that Identity answers at its key-set address."
        )
    else:
        name, ready_message = "Authentik signing keys", "Connected with verified TLS"
        failed_message = "Check Authentik, OIDC configuration and trusted TLS certificates."
    try:
        verifier = request.app.state.token_verifier
        if verifier is None:
            raise RuntimeError("OIDC unavailable")
        response = await request.app.state.oidc_http.get(verifier.config.jwks_url)
        response.raise_for_status()
        if not response.json().get("keys"):
            raise ValueError("Missing keys")
        checks.append(SetupCheck(name=name, status="ready", message=ready_message))
    except Exception:
        checks.append(SetupCheck(name=name, status="failed", message=failed_message))
    return SetupChecks(
        ready=all(c.status != "failed" for c in checks),
        checks=checks,
        countries=countries,
        currencies=currencies,
        languages=languages,
        timezones=timezones,
    )


@router.get("/administrator", response_model=SetupAdministrator)
async def administrator(
    request: Request,
    x_setup_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> SetupAdministrator:
    setup.check_key(request.app.state.settings, x_setup_key)
    claims = await verified_claims(request, authorization)
    return SetupAdministrator(email=setup.check_administrator(claims))


@router.post("/complete", response_model=SetupResult)
async def complete(
    body: SetupRequest,
    request: Request,
    x_setup_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> SetupResult:
    setup.check_key(request.app.state.settings, x_setup_key)
    claims = await verified_claims(request, authorization)
    async with request.app.state.session_factory() as db, db.begin():
        return await setup.provision(db, body, claims)
