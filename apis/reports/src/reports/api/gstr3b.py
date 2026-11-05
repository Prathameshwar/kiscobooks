"""GST applicability, preparation review and recorded external filing evidence."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.listing import PageMeta
from fastapi import Depends, Query, Request
from reporting_contract.gst import CATEGORIES
from sqlalchemy import select

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.api.framework_runs import authorize_job
from reports.api.routes import codec
from reports.domain.gstr3b import CALCULATION_VERSION, RULE_VERSION, applicable
from reports.models.framework import ReportJob
from reports.models.gst_return_review import GstReturnReview
from reports.schemas.framework import ResultPage
from reports.schemas.gstr3b import GstContext, GstReviewHistory, GstReviewItem, GstReviewRequest
from reports.tasks.access import authorize, can_prepare_gst
from reports.tasks.common import audit, company_lock, get


@router.get("/gst-return-context", response_model=GstContext)
async def context(current: Annotated[Access, Depends(access)]) -> GstContext:
    authorize(current)
    target = ScopePath(company_id=current.context.company_id)
    return GstContext(
        calculation_version=CALCULATION_VERSION,
        registrations=[row for row in current.context.registrations if applicable(row)],
        can_configure=current.actor.impersonation_id is None
        and current.actor.allows_scope("company.tax_registration.manage", target=target),
        can_capture=current.actor.impersonation_id is None
        and current.actor.allows_scope("ledger.post_journal", target=target),
        can_review=current.actor.impersonation_id is None
        and current.actor.allows_scope("accounting.finance.manage", target=target),
        rule_version=RULE_VERSION,
        can_prepare=can_prepare_gst(current),
    )


@router.get("/report-runs/{job_id}/gst-records", response_model=ResultPage)
async def records(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
    q: Annotated[str, Query(max_length=120)] = "",
    category: Annotated[str, Query(max_length=32)] = "",
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResultPage:
    from reports.api.framework_runs import result_row
    from reports.queries.results import batches

    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            job = await get(db, company_id, ReportJob, job_id)
            authorize_job(current, job)
            if job.status != "COMPLETE" or job.definition["code"] != "GSTR3B":
                raise ConflictError("complete GSTR-3B preparation required")
            aggregate = {
                "4A": {"4A1", "4A2", "4A3", "4A4", "4A5"},
                "4B": {"4B1", "4B2"},
                "4C": {"4A1", "4A2", "4A3", "4A4", "4A5", "4B1", "4B2"},
            }
            if category and category not in CATEGORIES and category not in aggregate:
                raise ValidationFailedError("unknown statutory table filter")
            matching = aggregate.get(category, {category})
            signer = codec(request, current, f"gst.records:{job_id}:{job.attempt}:{q}:{category}")
            after = 0 if cursor is None else signer.decode(cursor).get("after")
            if type(after) is not int or after < 0:
                raise ValidationFailedError("invalid source record cursor")
            ordinal = 0
            selected = []
            async for page in batches(db, job):
                for value in page:
                    ordinal += 1
                    if ordinal <= after:
                        continue
                    if category and value.get("category") not in matching:
                        continue
                    searchable = " ".join(
                        str(value.get(key, ""))
                        for key in ("reference", "category", "explanation", "source_id")
                    )
                    if q.casefold() not in searchable.casefold():
                        continue
                    selected.append(result_row(request, current, job, ordinal, value))
                    if len(selected) > limit:
                        return ResultPage(
                            items=selected[:limit],
                            page=PageMeta(
                                limit=limit,
                                has_more=True,
                                next_cursor=signer.encode({"after": selected[limit - 1].ordinal}),
                            ),
                        )
            return ResultPage(
                items=selected, page=PageMeta(limit=limit, has_more=False, next_cursor=None)
            )


@router.get("/report-runs/{job_id}/gst-review", response_model=GstReviewHistory)
async def history(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
) -> GstReviewHistory:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            job = await get(db, company_id, ReportJob, job_id)
            authorize_job(current, job)
            if job.definition["code"] != "GSTR3B":
                raise ValidationFailedError("review applies to GSTR-3B preparations")
            rows = list(
                await db.scalars(
                    select(GstReturnReview)
                    .where(
                        GstReturnReview.company_id == company_id, GstReturnReview.job_id == job_id
                    )
                    .order_by(GstReturnReview.id)
                    .limit(3)
                )
            )
            return GstReviewHistory(
                items=[
                    GstReviewItem.model_validate(
                        {name: getattr(row, name) for name in GstReviewItem.model_fields}
                    )
                    for row in rows
                ]
            )


@router.post("/report-runs/{job_id}/gst-review", response_model=GstReviewItem, status_code=201)
async def review(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    body: GstReviewRequest,
    request: Request,
    current: Annotated[Access, Depends(access)],
) -> GstReviewItem:
    authorize(current, "accounting.finance.manage")
    if current.actor.impersonation_id is not None:
        raise ConflictError("support sessions are read only")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await company_lock(db, current.actor.tenant_id, company_id)
            job = await get(db, company_id, ReportJob, job_id)
            authorize_job(current, job)
            # Lock the native job to serialize review events. No completed job fields are changed.
            await db.execute(
                select(ReportJob.id)
                .where(ReportJob.company_id == company_id, ReportJob.id == job_id)
                .with_for_update()
            )
            if job.status != "COMPLETE" or job.definition["code"] != "GSTR3B" or not job.result:
                raise ConflictError("review requires a completed GSTR-3B preparation")
            evidence = job.result["evidence"]["gstr3b"]
            if evidence["issues"]:
                raise ConflictError(
                    "resolve return readiness and reconciliation exceptions before review"
                )
            existing = list(
                await db.scalars(
                    select(GstReturnReview)
                    .where(
                        GstReturnReview.company_id == company_id, GstReturnReview.job_id == job_id
                    )
                    .limit(3)
                )
            )
            if any(row.state == body.state for row in existing):
                row = next(row for row in existing if row.state == body.state)
                if (
                    row.reference != body.reference
                    or row.evidence_hash != body.evidence_hash
                    or row.filed_date != body.filed_date
                ):
                    raise ConflictError("recorded GST review evidence is immutable")
                return GstReviewItem.model_validate(
                    {name: getattr(row, name) for name in GstReviewItem.model_fields}
                )
            if evidence.get("calculation_version") != CALCULATION_VERSION:
                raise ConflictError(
                    "prepare this return with the current reviewed calculations "
                    "before review or filing"
                )
            if body.state == "EXTERNALLY_FILED":
                already_filed = await db.scalar(
                    select(GstReturnReview.id).where(
                        GstReturnReview.company_id == company_id,
                        GstReturnReview.filed_period_key
                        == job.parameters["registration_id"] + ":" + job.parameters["period"],
                    )
                )
                if already_filed is not None:
                    raise ConflictError(
                        "this GSTIN and return period already has external filing evidence"
                    )
                if (
                    not body.filed_date
                    or not dt.date.fromisoformat(evidence["date_to"])
                    < body.filed_date
                    <= dt.date.today()
                ):
                    raise ValidationFailedError(
                        "external filing requires a valid acknowledgement date"
                    )
                if not any(row.state == "REVIEWED" for row in existing):
                    raise ConflictError(
                        "review this frozen preparation before recording external filing"
                    )
                if any(
                    Decimal(values[key]) != 0
                    for values in evidence["payment"].values()
                    for key in (
                        "normal_unpaid",
                        "rcm_unpaid",
                        "eco_unpaid",
                        "interest_unpaid",
                        "late_fee_unpaid",
                    )
                ):
                    raise ConflictError("external filing requires reconciled liability offsets")
            row = GstReturnReview(
                tenant_id=current.actor.tenant_id,
                company_id=company_id,
                job_id=job_id,
                registration_id=uuid.UUID(job.parameters["registration_id"]),
                period=job.parameters["period"],
                **body.model_dump(),
                filed_period_key=job.parameters["registration_id"] + ":" + job.parameters["period"]
                if body.state == "EXTERNALLY_FILED"
                else None,
                created_by=current.actor.user_id,
                updated_by=current.actor.user_id,
            )
            db.add(row)
            await db.flush()
            audit(
                db,
                row.tenant_id,
                company_id,
                row.id,
                "gst." + body.state.lower(),
                current.actor.user_id,
            )
            return GstReviewItem.model_validate(
                {name: getattr(row, name) for name in GstReviewItem.model_fields}
            )
