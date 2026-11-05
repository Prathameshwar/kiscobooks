"""Accounting-only signed stock reporting source with explicit company scopes."""

import datetime as dt
import uuid

from billing_platform.db import tenant_scope
from billing_platform.errors import PlatformError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import (
    authenticate_snapshot,
    require_snapshot_scope,
    response_headers,
)
from fastapi import APIRouter, Request, Response
from pydantic import Field, ValidationError
from reporting_contract.catalog_stock import CatalogStockPage
from reporting_contract.contract import Contract
from reporting_contract.enrollment import scope_allowed

from catalog.tasks.stock_report_sources import page

router = APIRouter()


class SourceRequest(Contract):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    source_id: uuid.UUID
    as_of: dt.date
    offset: int = Field(default=0, ge=0, le=10000)
    release: bool = False


@router.post("/internal/v1/stock-report-sources", include_in_schema=False)
async def stock_report_sources(request: Request) -> Response:
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 4096:
            raise ValidationFailedError(
                "stock report source request exceeds its transport contract"
            )
    raw = bytes(payload)
    if request.url.query:
        raise ValidationFailedError("stock report source request exceeds its transport contract")
    credential, framed, key_id = authenticate_snapshot(
        request.app.state.settings.stock_report_credentials,
        owner="catalog",
        requester="accounting",
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query="",
        body=raw,
    )
    try:
        body = SourceRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid stock report source request") from exc
    status = 200
    try:
        allowed = await scope_allowed(
            credential,
            request.app.state.settings.report_enrollment_source,
            body.tenant_id,
            body.company_id,
        )
        require_snapshot_scope(
            credential, tenant_id=body.tenant_id, company_id=body.company_id, enrolled=allowed
        )
        with tenant_scope(body.tenant_id):
            async with request.app.state.session_factory.begin() as db:
                value = await page(
                    db,
                    tenant=body.tenant_id,
                    company=body.company_id,
                    identity=body.source_id,
                    as_of=body.as_of,
                    offset=body.offset,
                    release=body.release,
                )
                value = CatalogStockPage.model_validate(value).model_dump(mode="json")
    except PlatformError as exc:
        value, status = exc.envelope().model_dump(mode="json"), exc.status_code
    response_body = canonical_json(value)
    return Response(
        response_body,
        status_code=status,
        media_type="application/json",
        headers=response_headers(
            credential,
            owner="catalog",
            requester="accounting",
            key_id=key_id,
            request_bytes=framed,
            body=response_body,
        ),
    )
