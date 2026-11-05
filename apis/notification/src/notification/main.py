from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from billing_platform.db import create_engine
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError
from billing_platform.rate_limit import WindowLimiter
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from notification.api.control import router as control_router
from notification.api.management import router as management_router
from notification.api.routes import router as api_router
from notification.callback_logging import CallbackQueryRedaction
from notification.callbacks import router as callback_router
from notification.config import Settings
from notification.credentials import resolve_secret
from notification.ownership import current_space
from notification.ownership import session_factory as notification_session_factory


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()  # type: ignore[call-arg]
    app = FastAPI(title="Notification API", version="1.0.0", lifespan=_lifespan)
    app.add_middleware(CallbackQueryRedaction)
    app.state.settings = configuration
    app.state.engine = create_engine(configuration.database_url)
    app.state.engine.sync_engine.hide_parameters = True
    app.state.session_factory = notification_session_factory(app.state.engine)
    data_key = configuration.data_encryption_key.get_secret_value().encode()
    app.state.data_key = data_key if len(data_key) == 32 else hashlib.sha256(data_key).digest()

    def bound_secret(reference: str | None) -> bytes:
        selected_space = current_space()
        if not reference or selected_space is None:
            raise RuntimeError("callback secret binding is unavailable")
        return resolve_secret(
            configuration, reference, tenant_id=require_current_tenant(), space_id=selected_space
        )

    app.state.secret_resolver = bound_secret
    app.state.callback_limiter = WindowLimiter()
    app.include_router(api_router, prefix="/v1")
    app.include_router(management_router, prefix="/v1")
    app.include_router(api_router, prefix="/v1/platform")
    app.include_router(management_router, prefix="/v1/platform")
    app.include_router(control_router, prefix="/v1")
    app.include_router(control_router, prefix="/v1/platform")
    app.include_router(callback_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(request.headers.get("x-trace-id")).model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        invalid = ValidationFailedError(
            "invalid request",
            fields={
                ".".join(str(x) for x in error["loc"]): "invalid value" for error in exc.errors()
            },
        )
        return JSONResponse(
            status_code=422,
            content=invalid.envelope(request.headers.get("x-trace-id")).model_dump(
                exclude_none=True
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # A unique-constraint collision (e.g. re-uploading identical template content)
        # is a clean 409, never a raw driver 500 with SQL in it (CLAUDE.md §5.8).
        conflict = ConflictError("this conflicts with an existing record")
        return JSONResponse(
            status_code=conflict.status_code,
            content=conflict.envelope(request.headers.get("x-trace-id")).model_dump(
                exclude_none=True
            ),
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        failure = PlatformError("notification request failed")
        return JSONResponse(
            status_code=500,
            content=failure.envelope(request.headers.get("x-trace-id")).model_dump(
                exclude_none=True
            ),
        )

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
