"""Read-only company overview; complete-input authority applies to every total."""

import datetime as dt
import uuid
from typing import Annotated
from zoneinfo import ZoneInfo

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from fastapi import Depends, Request
from sqlalchemy import select

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.models.core import ReportGeneration
from reports.schemas.overview import CompanyOverview
from reports.tasks.access import authorize
from reports.tasks.common import get
from reports.tasks.overview import calculate_overview


@router.get("/overview", response_model=CompanyOverview)
async def overview(
    request: Request,
    current: Annotated[Access, Depends(access)],
    generation_id: uuid.UUID | None = None,
    fiscal_year_id: uuid.UUID | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> CompanyOverview:
    authorize(current)
    allowed = {"generation_id", "fiscal_year_id", "date_from", "date_to"}
    if set(request.query_params) - allowed or len(request.query_params) != len(
        request.query_params.multi_items()
    ):
        raise ValidationFailedError("unsupported overview query")
    if current.context.finance is None:
        raise ConflictError("current company financial context is required")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            company = current.context.company_id
            generation = (
                await get(db, company, ReportGeneration, generation_id)
                if generation_id
                else await db.scalar(
                    select(ReportGeneration)
                    .where(
                        ReportGeneration.company_id == company, ReportGeneration.status == "READY"
                    )
                    .order_by(ReportGeneration.id.desc())
                    .limit(1)
                )
            )
            if generation is None or generation.status != "READY":
                raise ConflictError(
                    "the company's verified report source is still being prepared"
                )
            result = await calculate_overview(
                db,
                generation,
                fiscal_year_id=fiscal_year_id,
                date_from=date_from,
                date_to=date_to,
                today=dt.datetime.now(ZoneInfo(current.context.finance.timezone)).date(),
            )
            if result.currency != current.context.base_currency:
                raise ConflictError("company currency changed; refresh the financial source")
    return result
