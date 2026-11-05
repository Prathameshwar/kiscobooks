"""Company-scoped frozen hierarchy access with live authority and parent-bound cursors."""

import uuid
from typing import Annotated

from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.listing import PageMeta
from fastapi import Depends, Query, Request, Response

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.api.framework_runs import authorize_job, result_row
from reports.api.routes import codec
from reports.models.framework import ReportJob
from reports.queries.hierarchy import branch, summaries
from reports.schemas.trial_balance import (
    TrialHierarchyPage,
    TrialHierarchyRow,
    TrialNode,
)
from reports.schemas.trial_balance_options import NODE_PATTERN, Period
from reports.tasks.access import authorize
from reports.tasks.common import get


@router.get("/report-runs/{identity}/hierarchy", response_model=TrialHierarchyPage)
async def hierarchy(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    response: Response,
    current: Annotated[Access, Depends(access)],
    parent: Annotated[
        str, Query(pattern=r"^(?:root|" + NODE_PATTERN[1:-1] + r")$", max_length=48)
    ] = "root",
    period: Period = "CURRENT",
    show_zero: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> TrialHierarchyPage:
    authorize(current, "report.read")
    response.headers["Cache-Control"] = "no-store"
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            job = await get(db, company_id, ReportJob, identity)
            authorize_job(current, job)
            totals = summaries(job)
            signer = codec(
                request,
                current,
                f"trial-hierarchy:{identity}:{job.attempt}:{period}:{parent}:{show_zero}",
            )
            after = signer.decode(cursor).get("after") if cursor else 0
            if type(after) is not int:
                raise ValidationFailedError("invalid hierarchy cursor")
            values, more = await branch(db, job, period, parent, show_zero, limit, after)
            items = []
            for ordinal, raw in values:
                retained = result_row(request, current, job, ordinal, raw)
                items.append(
                    TrialHierarchyRow(
                        ordinal=ordinal,
                        data=TrialNode.model_validate(
                            {key: raw[key] for key in TrialNode.model_fields if key in raw}
                        ),
                        drilldowns=retained.drilldowns,
                    )
                )
            return TrialHierarchyPage(
                items=items,
                summary=totals[period],
                periods=tuple(totals),
                page=PageMeta(
                    limit=limit,
                    has_more=more,
                    next_cursor=signer.encode({"after": values[-1][0]}) if more else None,
                ),
            )
