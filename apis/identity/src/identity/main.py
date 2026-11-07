"""The `identity` FastAPI application factory.

Thin by design (CLAUDE.md §4): it wires the engine and session factory onto
``app.state``, registers the one exception handler that turns any ``PlatformError``
into the shared error envelope — no stack trace, no SQL, no internal id ever reaches a
client (CLAUDE.md §5.8) — mounts the resource routers, and exposes liveness/readiness.
All business logic lives in the routers and ``domain/``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from billing_platform.db import create_engine, create_session_factory
from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError
from billing_platform.fields import registry
from billing_platform.oidc import AccessTokenVerifier
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from identity import models
from identity.api import (
    company_gst_filing,  # noqa: F401 registers company setup routes
    company_gst_outward,  # noqa: F401 registers scoped outward reporting setup
)
from identity.api.banks import router as banks_router
from identity.api.catalog_authorizations import router as catalog_authorizations_router
from identity.api.catalog_enrollments import router as catalog_enrollments_router
from identity.api.catalog_sources import router as catalog_sources_router
from identity.api.children import router as children_router
from identity.api.companies import router as companies_router
from identity.api.company_currency import router as company_currency_router
from identity.api.company_statutory import router as company_statutory_router
from identity.api.customization import router as customization_router
from identity.api.documents import router as documents_router
from identity.api.impersonation import router as impersonation_router
from identity.api.invitations import router as invitations_router
from identity.api.lifecycle import router as lifecycle_router
from identity.api.login import router as login_router
from identity.api.onboarding import router as onboarding_router
from identity.api.org import router as org_router
from identity.api.platform import router as platform_router
from identity.api.platform_access import router as platform_access_router
from identity.api.platform_accounts import router as platform_accounts_router
from identity.api.platform_pricing import router as platform_pricing_router
from identity.api.posting import router as posting_router
from identity.api.reference import router as reference_router
from identity.api.reference_management import router as reference_management_router
from identity.api.reference_source import router as reference_source_router
from identity.api.registration import router as registration_router
from identity.api.report_authorizations import router as report_authorizations_router
from identity.api.report_enrollments import router as report_enrollments_router
from identity.api.roles import router as roles_router
from identity.api.setup import router as setup_router
from identity.api.step_up import router as step_up_router
from identity.api.tenants import router as tenants_router
from identity.api.tokens import router as tokens_router
from identity.api.users import router as users_router
from identity.config import Settings
from identity.domain import field_registry  # noqa: F401  registers identity.* native fields
from identity.metadata import MIGRATION_HEAD, TABLES


def _assert_field_registry_matches_models() -> None:
    """Boot check (docs/identity-schema.md §6.2): every registered native-field key
    resolves to a real column. Drift is a boot failure, not a form that silently drops
    a field — the same rule as an unknown seeded permission key."""
    model_map = {
        registry.get(entity_type).model_name: getattr(models, registry.get(entity_type).model_name)
        for entity_type in registry.entity_types()
    }
    problems = registry.validate_against_models(model_map)
    if problems:
        raise RuntimeError("native field registry drifted from the models: " + "; ".join(problems))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # One Redis client is shared by proofs, grants and reference choices; close it once
    # here rather than through either wrapper, so neither double-closes the other's client.
    if app.state.redis is not None:
        await app.state.redis.aclose()
    if app.state.document_store is not None:
        await app.state.document_store.close()
    await app.state.oidc_http.aclose()
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    _assert_field_registry_matches_models()
    configuration = settings or Settings()  # type: ignore[call-arg]
    app = FastAPI(title="Identity API", version="1.0.0", lifespan=_lifespan)
    app.state.settings = configuration
    import hashlib

    from billing_platform.rate_limit import WindowLimiter

    app.state.auth_limiter = WindowLimiter()
    # The local provider's throttles are keyed on text a caller chooses (an email, a request id), so
    # they get their own, larger table: filling it must not lock the middleware's window out. The
    # table is wiped every minute.
    app.state.local_limiter = WindowLimiter(capacity=65_536)

    @app.middleware("http")
    async def platform_diagnostics(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith(("/v1/platform/", "/v1/setup/")):
            return await call_next(request)
        import logging
        import uuid

        from billing_platform.audit_context import audit_request
        from billing_platform.diagnostics import log_failure

        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        with audit_request(request.headers.get("x-trace-id"), request_id):
            try:
                response = await call_next(request)
            except Exception as exc:
                log_failure(
                    logging.getLogger(__name__),
                    service="identity",
                    event="platform.request_failed",
                    error=exc,
                    trace_id=request.headers.get("x-trace-id"),
                )
                # The owning transaction has rolled back before this boundary.
                # Do not let ASGI's exception logger print SQL/profile/secret text.
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {"code": "internal_error", "message": "Platform request failed"}
                    },
                    headers={"Cache-Control": "no-store", "X-Request-Id": request_id},
                )
            if response.status_code >= 500:
                log_failure(
                    logging.getLogger(__name__),
                    service="identity",
                    event="platform.dependency_failed",
                    error=RuntimeError(),
                    trace_id=request.headers.get("x-trace-id"),
                )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-Id"] = request_id
        return response

    @app.middleware("http")
    async def auth_rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        sensitive = (
            request.url.path == "/internal/v1/gateway/authorize"
            or request.url.path.startswith("/v1/session")
            or "/invitations" in request.url.path
            or "/step-up/" in request.url.path
            or "/identities" in request.url.path
            or request.url.path.startswith("/v1/setup/")
            or request.url.path.startswith("/v1/onboarding/")
            or request.url.path.startswith("/v1/registration/")
            or request.url.path.startswith("/v1/platform/")
            # The sign-in page's address is the only one `/oidc/authorize` sees per person. Calls
            # the Auth app makes on everyone's behalf (`/oidc/token`, `/oidc/revoke`,
            # `/internal/v1/local-auth/*`) all arrive from its one address, so a per-address window
            # here would be one budget for the whole installation; they are throttled per account,
            # per request and per forwarded client instead.
            or request.url.path == "/oidc/authorize"
        )
        if sensitive:
            address = request.client.host if request.client else "unknown"
            credential = request.headers.get("authorization", "")[:16384]
            limiter = request.app.state.auth_limiter
            if not limiter.allow(
                hashlib.sha256(address.encode()).hexdigest(), limit=2400
            ) or not limiter.allow(
                hashlib.sha256((address + ":" + credential).encode()).hexdigest(), limit=120
            ):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "too many authentication requests",
                        }
                    },
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)

    app.state.engine = create_engine(configuration.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    from identity.services.provider_transport import provider_client

    app.state.oidc_http = provider_client(configuration)
    # A single Redis client backs proofs, permission caching and reference choices
    # (billing_platform.cache is the one place a client is constructed). Nothing else on
    # this platform uses Redis as a broker — it is cache-only (docs/tech-stack.md).
    from billing_platform.cache import RedisCache, create_redis_client

    app.state.redis = (
        create_redis_client(configuration.redis_url.get_secret_value())
        if configuration.redis_url
        else None
    )
    from identity.services.step_up import RedisProofStore

    app.state.proof_store = (
        RedisProofStore(app.state.redis) if app.state.redis is not None else None
    )
    from identity.services.authz_cache import NAMESPACE, GrantCache

    app.state.grant_cache = (
        GrantCache(
            RedisCache(app.state.redis, namespace=NAMESPACE),
            ttl_seconds=configuration.authz_cache_ttl_seconds,
        )
        if app.state.redis is not None
        else None
    )
    from identity.services.company_display_cache import CompanyDisplayCache
    from identity.services.company_display_cache import namespace as display_namespace
    from identity.services.reference_cache import ReferenceChoiceCache, namespace

    app.state.reference_cache = (
        ReferenceChoiceCache(
            RedisCache(app.state.redis, namespace=namespace(configuration.database_url)),
            ttl_seconds=configuration.reference_cache_ttl_seconds,
        )
        if app.state.redis is not None and configuration.reference_cache_ttl_seconds > 0
        else None
    )
    app.state.company_display_cache = (
        CompanyDisplayCache(
            RedisCache(
                app.state.redis,
                namespace=display_namespace(configuration.database_url),
            ),
            ttl_seconds=configuration.company_display_cache_ttl_seconds,
        )
        if app.state.redis is not None and configuration.company_display_cache_ttl_seconds > 0
        else None
    )
    from identity.services.documents import AzureDocumentStore

    app.state.document_store = (
        AzureDocumentStore(configuration.azure_blob) if configuration.azure_blob else None
    )
    app.state.token_verifier = (
        AccessTokenVerifier(configuration.oidc.configuration(), app.state.oidc_http)
        if configuration.oidc is not None
        else None
    )

    from identity.local_auth.service import LocalAuth

    # The provider that issues tokens runs inside this service; it is built once and shared.
    app.state.local_auth = (
        LocalAuth(configuration.local_auth)
        if configuration.auth_provider == "local" and configuration.local_auth is not None
        else None
    )

    from identity.api.commercial_salespeople import router as commercial_salespeople_router
    from identity.api.local_auth import internal as local_auth_internal_router
    from identity.api.local_auth import public as local_auth_public_router
    from identity.api.oidc import router as oidc_router
    from identity.api.voucher_sources import router as voucher_sources_router

    app.include_router(voucher_sources_router)
    from identity.api.voucher_enrollments import router as voucher_enrollments_router

    app.include_router(voucher_enrollments_router)
    from identity.api.stock_posting import router as stock_posting_router

    app.include_router(stock_posting_router)
    from identity.api.tracking_features import router as tracking_features_router

    app.include_router(tracking_features_router)
    app.include_router(commercial_salespeople_router)
    app.include_router(tenants_router)
    app.include_router(reference_management_router)
    app.include_router(reference_source_router)
    app.include_router(login_router)
    app.include_router(lifecycle_router)
    app.include_router(children_router)
    app.include_router(banks_router)
    app.include_router(company_currency_router)
    app.include_router(documents_router)
    app.include_router(tokens_router)
    app.include_router(platform_router)
    from identity.api.platform_roles import router as platform_roles_router

    app.include_router(platform_roles_router)
    app.include_router(platform_access_router)
    app.include_router(platform_pricing_router)
    app.include_router(platform_accounts_router)
    app.include_router(onboarding_router)
    app.include_router(registration_router)
    app.include_router(setup_router)
    app.include_router(customization_router)
    app.include_router(step_up_router)
    app.include_router(impersonation_router)
    app.include_router(posting_router)
    app.include_router(invitations_router)
    app.include_router(oidc_router)
    app.include_router(local_auth_internal_router)
    app.include_router(local_auth_public_router)
    app.include_router(companies_router)
    from identity.api.company_setup import commands_router as company_setup_commands_router
    from identity.api.company_setup import router as company_setup_router

    app.include_router(company_setup_router)
    app.include_router(company_setup_commands_router)
    app.include_router(reference_router)
    app.include_router(company_statutory_router)
    app.include_router(org_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(catalog_sources_router)
    app.include_router(catalog_enrollments_router)
    app.include_router(catalog_authorizations_router)
    app.include_router(report_authorizations_router)
    app.include_router(report_enrollments_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(request.headers.get("x-trace-id")).model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def request_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never return input values or validator context (which may contain personal data).
        fields = {
            ".".join(str(part) for part in issue["loc"]): issue["type"] for issue in exc.errors()
        }
        return await platform_error(
            request, ValidationFailedError("request validation failed", fields=fields)
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # A unique-constraint race that slipped past a route's pre-check (or a path with
        # no pre-check) reaches here as an IntegrityError. Map it to a clean 409 envelope
        # rather than leaking a driver 500 with SQL in it (CLAUDE.md §5.8). The detail is
        # deliberately generic — the constraint name would be an internal identifier.
        conflict = ConflictError("this conflicts with an existing record")
        return JSONResponse(
            status_code=conflict.status_code,
            content=conflict.envelope(request.headers.get("x-trace-id")).model_dump(
                exclude_none=True
            ),
        )

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        try:
            async with asyncio.timeout(3):
                async with app.state.engine.connect() as connection:
                    names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                    if not (TABLES | {"alembic_version"}) <= set(names):
                        raise RuntimeError("schema incomplete")
                    heads = (
                        (await connection.execute(text("SELECT version_num FROM alembic_version")))
                        .scalars()
                        .all()
                    )
                    if heads != [MIGRATION_HEAD]:
                        raise RuntimeError("migration version differs")
        except (SQLAlchemyError, RuntimeError, TimeoutError):
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "dependency_unavailable",
                        "message": "database is not ready",
                        "trace_id": request.headers.get("x-trace-id"),
                    }
                },
            )
        return JSONResponse({"status": "ready"})

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
