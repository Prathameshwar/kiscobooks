"""Accounting HTTP boundary with private failures and truthful database readiness."""

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
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from accounting.config import Settings
from accounting.metadata import MIGRATION_HEAD, TABLES


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code, message=message, trace_id=safe_trace_id(request.headers.get("x-trace-id"))
        )
    )
    return JSONResponse(status_code=status, content=envelope.model_dump(exclude_none=True))


class FailureBoundary:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        parts = scope["path"].split("/")
        if (
            scope["method"] == "POST"
            and parts[1:3] == ["v1", "companies"]
            and (
                parts[4:6] == ["stock", "openings"]
                or parts[4:5] in (["opening-batches"], ["financial-opening-imports"])
            )
        ):
            pieces: list[bytes] = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > (3_145_728 if parts[4:5] == ["financial-opening-imports"] else 2_097_152):
                    await error(
                        Request(scope),
                        413,
                        "payload_too_large",
                        "opening request exceeds its byte limit",
                    )(scope, receive, send)
                    return
                pieces.append(chunk)
                if not message.get("more_body", False):
                    break
            original_receive = receive
            supplied = False

            async def opening_receive() -> Message:
                nonlocal supplied
                if not supplied:
                    supplied = True
                    return {"type": "http.request", "body": b"".join(pieces), "more_body": False}
                return await original_receive()

            receive = opening_receive
        started = False

        async def tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if parts[1:3] == ["v1", "companies"] and parts[4:5] in (
                    ["opening-batches"],
                    ["financial-opening-imports"],
                ):
                    headers = [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"cache-control"
                    ]
                    message["headers"] = [*headers, (b"cache-control", b"private, no-store")]
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception as exc:
            request = Request(scope)
            log_failure(
                logging.getLogger("accounting.http"),
                service="accounting",
                event="http.unexpected_failure",
                error=exc,
                trace_id=safe_trace_id(request.headers.get("x-trace-id")),
            )
            if started:
                raise RuntimeError("response stream failed") from None
            await error(request, 500, "internal_error", "request could not be completed")(
                scope, receive, send
            )


def create_app(settings: Settings | None = None, *, engine: AsyncEngine | None = None) -> FastAPI:
    from accounting.tasks import reporting_feed  # noqa: F401 - register commit capture

    configuration = settings if settings is not None else Settings.model_validate({})
    database = engine if engine is not None else create_engine(configuration.database_url)

    from accounting.tasks.posting_delivery import connection

    posting_connection = connection(configuration)
    from accounting.tasks.stock_identity import connection as stock_identity_connection

    stock_posting_connection = stock_identity_connection(configuration)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if posting_connection is not None:
                await posting_connection[0].aclose()
            if stock_posting_connection is not None:
                await stock_posting_connection[0].aclose()
            if engine is None:
                await database.dispose()

    app = FastAPI(title="Accounting API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(FailureBoundary)
    app.state.settings = configuration
    app.state.posting_client = posting_connection[1] if posting_connection is not None else None
    app.state.stock_posting_client = (
        stock_posting_connection[1] if stock_posting_connection is not None else None
    )
    app.state.tracking_feature_client = (
        stock_posting_connection[1].client if stock_posting_connection is not None else None
    )
    app.state.engine = database
    app.state.session_factory = create_session_factory(database, guarded=True)
    app.state.write_limiter = WindowLimiter()
    from accounting.api.reporting_snapshot import router as reporting_snapshot_router

    app.include_router(reporting_snapshot_router)
    from accounting.api.stock_execution import router as stock_execution_router
    from accounting.api.stock_tracking import router as stock_tracking_router

    app.include_router(stock_tracking_router)
    app.include_router(stock_execution_router)
    from accounting.api.stock import router as stock_router
    from accounting.api.stock_opening import router as stock_opening_router

    app.include_router(stock_opening_router)
    app.include_router(stock_router)
    from accounting.api.stock_retirement import router as stock_retirement_router

    app.include_router(stock_retirement_router)
    from accounting.api.stock_policy import router as stock_policy_router

    app.include_router(stock_policy_router)
    from accounting.tasks.voucher_tax import configure

    configure(configuration.utgst_states)
    from accounting.api.charges import router as charges_router
    from accounting.api.configuration import router as configuration_router
    from accounting.api.credit import router as credit_router
    from accounting.api.exchange_rates import router as exchange_rates_router
    from accounting.api.exports import router as exports_router
    from accounting.api.fiscal import router as fiscal_router
    from accounting.api.ledger import router as ledger_router
    from accounting.api.mapping_drafts import router as mapping_drafts_router
    from accounting.api.masters import router
    from accounting.api.party_drug_licences import router as party_drug_licences_router
    from accounting.api.setup import router as setup_router
    from accounting.api.subledger import router as subledger_router
    from accounting.api.voucher_execution import router as voucher_execution_router
    from accounting.api.voucher_sources import router as voucher_sources_router
    from accounting.api.voucher_tax import router as voucher_tax_router
    from accounting.api.withholding import router as withholding_router
    from accounting.api.workflows import router as workflows_router

    app.include_router(voucher_sources_router)
    app.include_router(voucher_execution_router)
    from accounting.api.bank_reconciliation import router as bank_reconciliation_router
    from accounting.api.banking import router as banking_router

    app.include_router(banking_router)
    app.include_router(bank_reconciliation_router)
    from accounting.api.invoice_credit import router as invoice_credit_router

    app.include_router(invoice_credit_router)
    from accounting.api.gst_return import router as gst_return_router

    app.include_router(gst_return_router)
    from accounting.api.gst_outward import router as gst_outward_router

    app.include_router(gst_outward_router)
    from accounting.api.invoices import router as invoices_router

    app.include_router(invoices_router)
    app.include_router(charges_router)
    app.include_router(credit_router)
    app.include_router(fiscal_router)
    app.include_router(ledger_router)
    from accounting.api.financial_opening import router as financial_opening_router
    from accounting.api.financial_opening_import import router as financial_opening_import_router
    from accounting.api.party_opening import router as party_opening_router

    app.include_router(financial_opening_import_router)
    app.include_router(party_opening_router)
    from accounting.api.master_opening import router as master_opening_router

    app.include_router(master_opening_router)
    app.include_router(financial_opening_router)
    app.include_router(subledger_router)
    app.include_router(voucher_tax_router)
    app.include_router(exports_router)
    app.include_router(exchange_rates_router)
    app.include_router(setup_router)
    app.include_router(workflows_router)
    from accounting.api.master_imports import router as master_imports_router

    app.include_router(master_imports_router)
    app.include_router(mapping_drafts_router)
    app.include_router(withholding_router)
    from accounting.api.reporting import router as reporting_router

    app.include_router(reporting_router)
    app.include_router(party_drug_licences_router)
    from accounting.api.purchase_print import router as purchase_print_router

    app.include_router(purchase_print_router)
    app.include_router(router)
    app.include_router(configuration_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(safe_trace_id(request.headers.get("x-trace-id"))).model_dump(
                mode="json", exclude_none=True
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, 422, "validation_failed", "request validation failed")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(request, exc.status_code, "http_error", "request could not be handled")

    # Public infrastructure probes expose no company data or connection details.
    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        try:
            async with asyncio.timeout(configuration.database_check_timeout_seconds):
                async with database.connect() as connection:
                    names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                    if not (TABLES | {"alembic_version"}) <= set(names):
                        raise RuntimeError("schema incomplete")
                    heads = (
                        (await connection.execute(text("SELECT version_num FROM alembic_version")))
                        .scalars()
                        .all()
                    )
                    if heads != [MIGRATION_HEAD]:
                        raise RuntimeError("schema version differs")
                    if await connection.scalar(
                        text("SELECT 1 FROM accounting_setup WHERE metadata_version <> 1 LIMIT 1")
                    ):
                        raise RuntimeError("master metadata backfill incomplete")
        except (SQLAlchemyError, RuntimeError, TimeoutError):
            return error(request, 503, "dependency_unavailable", "Accounting database is not ready")
        return JSONResponse({"status": "ready"})

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
