"""Design HTTP application: truthful health probes and error envelopes.

Error responses carry the envelope and nothing else — no stack trace, no SQL, no
internal identifier (CLAUDE.md §5.8). The readiness probe is **truthful**: it reports
ready only when this service's own tables exist *and* the database is at the migration
revision this build expects, because a service answering requests against a half-migrated
schema is the failure mode a probe exists to catch.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from billing_platform.db import create_engine, create_session_factory
from billing_platform.diagnostics import log_failure, safe_trace_id
from billing_platform.errors import ErrorBody, ErrorEnvelope, PlatformError
from billing_platform.rate_limit import WindowLimiter
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException

from design.api.middleware import BodyLimit
from design.config import Settings
from design.metadata import MIGRATION_HEAD, TABLES


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    """Standardized error envelope response builder."""
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            trace_id=safe_trace_id(request.headers.get("x-trace-id")),
        )
    )
    return JSONResponse(
        status_code=status,
        content=envelope.model_dump(exclude_none=True),
        headers={"Cache-Control": "no-store"},
    )


def create_app(settings: Settings | None = None, *, engine: AsyncEngine | None = None) -> FastAPI:
    """Create and configure the FastAPI Invoice Designer application."""
    # Values come from the environment; mypy cannot see that, and there are no defaults.
    configuration = settings if settings is not None else Settings()  # type: ignore[call-arg]
    database = engine if engine is not None else create_engine(configuration.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is None:
                await database.dispose()

    app = FastAPI(title="Invoice Designer API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(BodyLimit)
    app.state.write_limiter = WindowLimiter()
    app.state.settings = configuration
    app.state.engine = database
    app.state.session_factory = create_session_factory(database, guarded=True)

    from design.api.routes import router as design_router

    app.include_router(design_router)
    from design.api.printing import router as printing_router

    app.include_router(printing_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            exc.envelope(safe_trace_id(request.headers.get("x-trace-id"))).model_dump(
                mode="json", exclude_none=True
            ),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's input/context may echo the request; never serialize it to the caller.
        return error(request, 422, "validation_failed", "request validation failed")

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return error(request, 409, "conflict", "a unique value in this request conflicts")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(request, exc.status_code, "http_error", "request could not be handled")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        log_failure(
            logging.getLogger("design.http"),
            service="design",
            event="http.unexpected_failure",
            error=exc,
            trace_id=safe_trace_id(request.headers.get("x-trace-id")),
        )
        return error(request, 500, "internal_error", "request could not be completed")

    # Public infrastructure probes. They return no tenant data and no schema detail.
    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        """Liveness: the process is up. It says nothing about the database."""
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        """Readiness: schema present and at this build's migration revision."""
        try:
            async with asyncio.timeout(configuration.database_check_timeout_seconds):
                async with database.connect() as connection:
                    names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                    if not (TABLES | {"alembic_version"}) <= set(names):
                        raise RuntimeError("design schema is incomplete")
                    heads = (
                        (await connection.execute(text("SELECT version_num FROM alembic_version")))
                        .scalars()
                        .all()
                    )
                    if list(heads) != [MIGRATION_HEAD]:
                        raise RuntimeError("design migration version differs")
        except (SQLAlchemyError, RuntimeError, TimeoutError):
            return error(request, 503, "dependency_unavailable", "database is not ready")
        return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
