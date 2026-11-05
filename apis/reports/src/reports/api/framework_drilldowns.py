"""Signed row mappings create an ordinary child run pinned to its parent's source."""

import uuid
from typing import Annotated

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from reports.api.auth import Access, access
from reports.api.framework import router
from reports.api.framework_runs import authorize_job, submit_run
from reports.api.routes import Idempotency, codec
from reports.models.framework import ReportJob
from reports.schemas.framework import (
    DrilldownOrigin,
    DrilldownRequest,
    FrameworkRunRequest,
    JobDetail,
)
from reports.tasks.common import get


@router.post("/report-runs/{identity}/drilldowns", response_model=JobDetail, status_code=202)
async def drilldown(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    body: DrilldownRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            parent = await get(db, company_id, ReportJob, identity)
            authorize_job(current, parent)
            if parent.kind != "RUN" or parent.status != "COMPLETE":
                raise ConflictError("completed drilldown parent required")
            selected = codec(request, current, f"v2.drilldown:{identity}:{parent.attempt}").decode(
                body.token
            )
            mappings = [
                value
                for value in parent.definition.get("drilldowns", ())
                if value["key"] == selected.get("mapping") and value["version"] == 1
            ]
            if (
                len(mappings) != 1
                or selected.get("mapping") == "row_detail"
                or type(selected.get("ordinal")) is not int
                or selected["ordinal"] < 1
                or not isinstance(selected.get("parameters"), dict)
            ):
                raise ValidationFailedError("invalid retained drilldown mapping")
            origin = DrilldownOrigin(
                parent_id=parent.id,
                parent_attempt=parent.attempt,
                ordinal=selected["ordinal"],
                mapping=selected["mapping"],
            )
            child = FrameworkRunRequest(
                code=mappings[0]["target"],
                generation_id=parent.generation_id,
                parameters=selected["parameters"],
            )
    return await submit_run(company_id, child, request, idempotency_key, current, origin)
