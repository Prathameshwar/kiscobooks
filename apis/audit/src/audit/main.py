"""The `audit` read API application factory.

Read-only HTTP: the trail, activity feed, security surface, and export. Ingestion is the
broker consumer (``tasks/consume``), not a route — there is no write API (docs/audit.md
§7 decision). Errors return the platform envelope only, never a stack trace or SQL
(CLAUDE.md §5.8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from billing_platform.db import create_engine, create_session_factory
from billing_platform.errors import PlatformError, ValidationFailedError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from audit.api.platform_events import router as platform_router
from audit.api.routes import router as api_router
from audit.config import Settings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()  # type: ignore[call-arg]
    app = FastAPI(title="Audit API", version="1.0.0", lifespan=_lifespan)
    app.state.settings = configuration
    app.state.engine = create_engine(configuration.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.include_router(api_router)
    app.include_router(platform_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(request.headers.get("x-trace-id")).model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return await platform_error(request, ValidationFailedError("invalid audit request"))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # ServerErrorMiddleware handles these outside the normal response middleware.
        return JSONResponse(
            status_code=500,
            content=PlatformError("Audit request failed").envelope().model_dump(exclude_none=True),
            headers={"Cache-Control": "no-store"},
        )

    @app.middleware("http")
    async def private_response(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> dict[str, str]:
        async with app.state.engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        return {"status": "ready"}

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
