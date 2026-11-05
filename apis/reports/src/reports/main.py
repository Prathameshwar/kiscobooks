"""Report HTTP application; no effects enabled merely by deploying the service."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from billing_platform.db import create_engine, create_session_factory
from billing_platform.errors import ErrorBody, ErrorEnvelope, PlatformError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException

from reports.config import Settings
from reports.metadata import MIGRATION_HEAD, TABLES


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        ErrorEnvelope(error=ErrorBody(code=code, message=message)).model_dump(exclude_none=True),
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def create_app(settings: Settings | None = None, *, engine: AsyncEngine | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings.model_validate({})
    database = engine if engine is not None else create_engine(configuration.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is None:
                await database.dispose()

    app = FastAPI(title="Reports API", version="0.1.0", lifespan=lifespan)
    from billing_platform.rate_limit import WindowLimiter

    from reports.api.middleware import BodyLimit

    app.add_middleware(BodyLimit)
    app.state.write_limiter = WindowLimiter()
    app.state.settings = configuration
    app.state.engine = database
    app.state.session_factory = create_session_factory(database, guarded=True)
    from reports.api import (  # noqa: F401 -- registers v2 routes
        framework_drilldowns,
        framework_exports,
        framework_lists,
        framework_runs,
        gstr1,
        gstr3b,
        overview,
        source_generations,
        source_readiness,
        stock_summary,
        trial_balance,
    )
    from reports.api.framework import router as framework_router
    from reports.api.routes import router
    from reports.tasks.report_catalog import catalog

    catalog()  # Validate versions, handlers, schemas, grains and metric dependencies at startup.
    app.include_router(router)
    app.include_router(framework_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            exc.envelope().model_dump(exclude_none=True),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(422, "validation_failed", "request validation failed")

    @app.exception_handler(IntegrityError)
    async def integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        return error(409, "conflict", "report reference or unique value conflicts")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(exc.status_code, "http_error", "request could not be handled")

    @app.exception_handler(Exception)
    async def failure(request: Request, exc: Exception) -> JSONResponse:
        import logging

        from billing_platform.diagnostics import log_failure

        log_failure(
            logging.getLogger("reports.http"),
            service="reports",
            event="http.unexpected_failure",
            error=exc,
        )
        return error(500, "internal_error", "request could not be completed")

    # Public infrastructure probes contain no tenant data or credentials.
    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        try:
            async with asyncio.timeout(configuration.database_check_timeout_seconds):
                async with database.connect() as connection:
                    names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                    if not TABLES | {"alembic_version"} <= set(names):
                        raise RuntimeError("schema incomplete")
                    heads = (
                        (await connection.execute(text("SELECT version_num FROM alembic_version")))
                        .scalars()
                        .all()
                    )
                    if heads != [MIGRATION_HEAD]:
                        raise RuntimeError("schema version differs")
        except (SQLAlchemyError, RuntimeError, TimeoutError):
            return error(503, "dependency_unavailable", "Reports database is not ready")
        return JSONResponse({"status": "ready", "checkpoint": "B09_FOUNDATION"})

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
