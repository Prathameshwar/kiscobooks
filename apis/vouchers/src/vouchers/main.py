"""Voucher HTTP application; no effects enabled merely by deploying the service."""

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

from vouchers.config import Settings
from vouchers.metadata import MIGRATION_HEAD, TABLES


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

    app = FastAPI(title="Vouchers API", version="0.1.0", lifespan=lifespan)
    from billing_platform.rate_limit import WindowLimiter

    from vouchers.api.middleware import BodyLimit

    app.add_middleware(BodyLimit)
    app.state.write_limiter = WindowLimiter()
    app.state.settings = configuration
    app.state.engine = database
    app.state.session_factory = create_session_factory(database, guarded=True)
    from vouchers.api.artifacts import router as artifacts_router
    from vouchers.api.counters import router as counters_router
    from vouchers.api.lifecycle import router as lifecycle_router
    from vouchers.api.routes import router
    from vouchers.api.sources import router as sources_router

    app.include_router(lifecycle_router)
    app.include_router(artifacts_router)
    from vouchers.api.results import router as results_router

    app.include_router(results_router)
    app.include_router(sources_router)
    from vouchers.api.company_defaults import router as company_defaults_router

    app.include_router(company_defaults_router)
    app.include_router(counters_router)
    from vouchers.api.posting import router as posting_router

    app.include_router(posting_router)
    from vouchers.api.stock_retirement import router as stock_retirement_router

    app.include_router(stock_retirement_router)
    from vouchers.api.invoices import router as invoice_router

    app.include_router(invoice_router)
    from vouchers.api.purchase_print import router as purchase_print_router

    app.include_router(purchase_print_router)
    from vouchers.api.supporting_files import router as supporting_files_router

    app.include_router(supporting_files_router)
    from vouchers.api.imports import router as imports_router

    # Before the generic /{resource} routes, which would otherwise shadow these paths.
    app.include_router(imports_router)
    from vouchers.api.stock_opening_import import router as stock_opening_import_router

    app.include_router(stock_opening_import_router)
    from vouchers.api.import_extensions import router as import_extensions_router

    app.include_router(import_extensions_router)
    from vouchers.api.day_book import router as day_book_router

    app.include_router(day_book_router)
    from vouchers.api.duplicate_bills import router as duplicate_bills_router

    # Before the generic /vouchers/{object_id} route, which would otherwise shadow this path.
    app.include_router(duplicate_bills_router)
    app.include_router(router)

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
        return error(409, "conflict", "voucher reference or unique value conflicts")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(exc.status_code, "http_error", "request could not be handled")

    @app.exception_handler(Exception)
    async def failure(request: Request, exc: Exception) -> JSONResponse:
        import logging

        from billing_platform.diagnostics import log_failure

        log_failure(
            logging.getLogger("vouchers.http"),
            service="vouchers",
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
            return error(503, "dependency_unavailable", "Vouchers database is not ready")
        return JSONResponse({"status": "ready", "checkpoint": "C0_FOUNDATION"})

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
