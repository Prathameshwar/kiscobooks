"""Native GST evidence commands; no mutable statutory total endpoint."""

import uuid

from billing_platform.db.access import company_object
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, Idempotency, no_query, response, session
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.gst_return import GstReturnRecord
from accounting.schemas.gst_return import GstCapture, GstRecordDetail
from accounting.tasks.access import authorize
from accounting.tasks.commands import protected
from accounting.tasks.finance_records import create_row
from accounting.tasks.financial_commands import FinancialEffect, financial_command
from accounting.tasks.gst_return import FIELDS, validate

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post("/gst-return-records", response_model=GstRecordDetail, status_code=201)
async def capture(
    company_id: uuid.UUID,
    body: GstCapture,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    spec = FINANCIAL_BY_NAME["gst_return_record"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        from decimal import Decimal

        from sqlalchemy import func, select

        from accounting.models.reporting import ReportChange

        sequence = (
            int(
                await db.scalar(
                    select(func.coalesce(func.max(ReportChange.sequence), 0)).where(
                        ReportChange.company_id == company_id
                    )
                )
                or 0
            )
            + 1
        )
        last = None
        for item in body.records:
            await validate(db, current, item)
            values = item.model_dump()
            for head in FIELDS:
                values[head] = Decimal(values[head])
            if values.get("conversion_rate") is not None:
                values["conversion_rate"] = Decimal(values["conversion_rate"])
            if item.category == "COVERAGE":
                values["covered_sequence"] = sequence
            last = await create_row(db, current, "gst_return_record", **values)
        assert last is not None
        return FinancialEffect(last)

    return response(
        request,
        await financial_command(
            request.app.state.session_factory,
            current,
            spec,
            "capture",
            body,
            idempotency_key,
            mutate,
            permission="ledger.post_journal",
            status=201,
        ),
    )


@router.get("/gst-return-records/{object_id}", response_model=GstRecordDetail)
async def get(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> object:
    spec = FINANCIAL_BY_NAME["gst_return_record"]
    authorize(current, spec, "read")
    row = await company_object(db, GstReturnRecord, object_id, company_id=company_id)
    return protected(row, spec, current)
