"""Readiness reports durable progress; reading it never starts an expensive build."""

import datetime as dt
from typing import Annotated
from zoneinfo import ZoneInfo

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from fastapi import Depends, Request
from sqlalchemy import select

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.models.core import ReportGeneration
from reports.models.readiness import ReportReadiness
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.native_context import NativeContext
from reports.schemas.readiness import SourceReadiness
from reports.tasks.access import authorize


@router.get("/source-readiness", response_model=SourceReadiness)
async def readiness(
    request: Request, current: Annotated[Access, Depends(access)]
) -> SourceReadiness:
    authorize(current)
    if request.query_params:
        raise ValidationFailedError("unsupported readiness query")
    company = current.context.company_id
    result = SourceReadiness(company_id=company, state="PREPARING")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            health = await db.scalar(
                select(ReportReadiness).where(ReportReadiness.company_id == company)
            )
            cut = await db.scalar(
                select(ReportSourceCut)
                .join(ReportGeneration, ReportGeneration.id == ReportSourceCut.generation_id)
                .where(
                    ReportSourceCut.company_id == company,
                    ReportGeneration.status == "READY",
                    ReportSourceCut.verification.is_not(None),
                )
                .order_by(ReportSourceCut.id.desc())
                .limit(1)
            )
            if health:
                result.owner_sequence, result.owner_checked_at = (
                    health.owner_sequence,
                    health.checked_at,
                )
                result.failure_code = health.failure_code
                if health.failure_code:
                    result.state = (
                        "DELAYED" if health.failure_code == "OWNER_UNAVAILABLE" else "NEEDS_ACTION"
                    )
            if not request.app.state.settings.automatic_sources_enabled:
                result.state, result.failure_code = "NEEDS_ACTION", "AUTOMATIC_PREPARATION_DISABLED"
            if cut is None:
                return result
            result.generation_id, result.verified_sequence = cut.generation_id, cut.sequence
            if not result.failure_code:
                result.state = (
                    "CURRENT" if health and health.owner_sequence == cut.sequence else "UPDATING"
                )
                if (
                    not health
                    or not health.checked_at
                    or health.checked_at < utcnow() - dt.timedelta(seconds=45)
                ):
                    result.state = "DELAYED"
            try:
                context = await NativeContext.load(db, company, cut.generation_id)
            except ConflictError:
                result.state, result.failure_code = "NEEDS_ACTION", "SOURCE_REVIEW_REQUIRED"
                return result
            finance = current.context.finance
            today = utcnow().astimezone(ZoneInfo(finance.timezone if finance else "UTC")).date()
            result.business_state = (
                "READY"
                if any(
                    r.get("status") == "FINALIZED"
                    for r in context.data.rows.get("opening_batch", {}).values()
                )
                else "OPENING_REQUIRED"
            )
            if context.coverage > today:
                result.business_state = "BOOKS_NOT_STARTED"
            elif not any(
                r.get("start_date", "~") <= today.isoformat() <= r.get("end_date", "")
                for r in context.data.rows.get("fiscal_year", {}).values()
            ):
                result.business_state = "YEAR_REQUIRED"
            # Financial and stock completeness are separate; absence of coverage
            # must never be presented as verified zero stock.
            rows = await db.execute(
                context.view.rows("inventory_report_record")
                .where(ReportFactVersion.inventory_kind == "COVERAGE")
                .limit(2)
            )
            for row in rows.scalars():
                payload = (row.data or {}).get("payload", {})
                if payload.get("kind") == "COVERAGE":
                    result.inventory_state = (
                        "READY"
                        if payload.get("as_of") == today.isoformat()
                        and payload.get("complete_company") is True
                        and payload.get("native_stock_current") is True
                        else "UPDATING"
                    )
                    break
    return result
