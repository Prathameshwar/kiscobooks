"""Scoped idempotent append-only outward evidence; no editable return totals."""

import uuid
from decimal import Decimal

from billing_platform.db.access import company_object
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, Idempotency, no_query, response, session
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.gst_outward import GstOutwardRecord
from accounting.models.reporting import ReportChange
from accounting.schemas.gst_outward import GstOutwardCapture, GstOutwardDetail
from accounting.tasks.access import authorize
from accounting.tasks.commands import protected
from accounting.tasks.finance_records import create_row
from accounting.tasks.financial_commands import FinancialEffect, financial_command
from accounting.tasks.gst_outward import validate

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post("/gst-outward-records", response_model=GstOutwardDetail, status_code=201)
async def capture(
    company_id: uuid.UUID,
    body: GstOutwardCapture,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    spec = FINANCIAL_BY_NAME["gst_outward_record"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
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
            values = item.model_dump(mode="json")
            values["registration_id"] = item.registration_id
            values["source_id"] = item.source_id
            values["original_record_id"] = item.original_record_id
            values["return_date"] = item.return_date
            values["document_date"] = item.document_date
            for head in ("invoice_value", "taxable", "igst", "cgst", "sgst", "cess"):
                values[head] = Decimal(values[head])
            if item.kind == "COVERAGE":
                values["details"]["covered_sequence"] = sequence
            last = await create_row(db, current, "gst_outward_record", **values)
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


@router.get("/gst-outward-records/{object_id}", response_model=GstOutwardDetail)
async def get(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> object:
    spec = FINANCIAL_BY_NAME["gst_outward_record"]
    authorize(current, spec, "read")
    row = await company_object(db, GstOutwardRecord, object_id, company_id=company_id)
    return protected(row, spec, current)
