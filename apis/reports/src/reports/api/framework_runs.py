"""Durable v2 commands and frozen rows; retrieval always checks current authority."""

import uuid
from dataclasses import asdict
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.display import DisplayConfiguration
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.listing import PageMeta
from fastapi import Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from reporting_contract.contract import Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.api.auth import Access, access
from reports.api.framework import resolve, router
from reports.api.routes import Idempotency, codec
from reports.domain.reporting.contracts import fingerprint as hash_value
from reports.domain.reporting.views import select as select_view
from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob, ReportResultBatch
from reports.queries.results import verify_batch
from reports.schemas.framework import (
    DrilldownLink,
    DrilldownOrigin,
    FrameworkRunRequest,
    JobDetail,
    ResultPage,
    ResultQuery,
    ResultRow,
)
from reports.tasks import framework_jobs as jobs
from reports.tasks import native_execution
from reports.tasks.access import authorize, fingerprint
from reports.tasks.common import audit, get
from reports.tasks.reference_source import source_count


def authorize_job(current: Access, row: ReportJob) -> None:
    authorize(current, "report.export" if row.kind == "EXPORT" else "report.read")
    # Authorize source requirements from the retained definition, even after a deployment.
    from billing_platform.authz import ScopePath

    for permission in row.definition["permissions"]:
        current.actor.require_scope(permission, target=ScopePath(company_id=row.company_id))
    if row.actor_id != current.actor.user_id or row.permission_hash != fingerprint(current):
        raise PermissionDeniedError("report belongs to a different permission context")


def detail(row: ReportJob) -> JobDetail:
    try:
        presentation = DisplayConfiguration.model_validate(row.display)
    except ValidationError:
        presentation = None  # Legacy results keep their exact values without invented formatting.
    return JobDetail.model_validate(
        {
            **{
                name: getattr(row, name)
                for name in JobDetail.model_fields
                if name
                not in {
                    "code",
                    "version",
                    "result",
                    "display",
                    "title",
                    "views",
                    "view",
                    "execution",
                    "delivery",
                }
            },
            "code": row.definition["code"],
            "version": row.definition["version"],
            "result": row.result if row.status == "COMPLETE" else None,
            "display": presentation,
            "title": row.definition["title"],
            "views": row.definition["views"],
            "view": (row.options or {}).get("view", "default"),
            "execution": (row.options or {}).get("execution", "STANDARD"),
            "delivery": row.parameters.get("delivery", "SINGLE")
            if row.kind == "EXPORT"
            else "SINGLE",
        }
    )


async def submit_run(
    company_id: uuid.UUID,
    body: FrameworkRunRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
    origin: DrilldownOrigin | None = None,
) -> JSONResponse:
    entry = resolve(current, body.code, body.version)
    if (
        body.code in {"TRIAL_BALANCE", "PROFIT_LOSS", "BALANCE_SHEET"}
        and entry.definition.version >= 6
        and (body.result_query is not None or body.execution != "STANDARD")
    ):
        raise ValidationFailedError(
            "financial statement views require complete-company standard inputs"
        )
    if body.code in {"GSTR3B", "GSTR1"}:
        from reports.tasks.access import can_prepare_gst

        if not can_prepare_gst(current):
            raise PermissionDeniedError("GST preparation authority is required")
    if body.result_query is not None and (origin is None or origin.mapping != "result_query"):
        raise ValidationFailedError("result queries require a completed parent")
    try:
        select_view(asdict(entry.definition)["views"], body.view)
    except ValueError:
        raise ValidationFailedError("requested report view is unavailable") from None
    if body.execution == "BULK" and body.code != "ACCOUNT_SUMMARY":
        raise ValidationFailedError("bulk calculation is available for account summaries")
    if not request.app.state.settings.framework_enabled:
        raise ConflictError("report framework admission is not enabled")
    try:
        parameters = entry.handler.normalize(body.parameters)
    except ValidationError as exc:
        raise ValidationFailedError("parameters do not match the report definition") from exc
    if body.code == "BALANCE_SHEET" and entry.definition.version >= 6:
        if (body.view == "comparison") != ("comparative_to" in parameters):
            raise ValidationFailedError("comparison date must match the Balance Sheet view")
    if body.code == "PROFIT_LOSS" and entry.definition.version >= 6:
        has_comparison = "comparative_from" in parameters and "comparative_to" in parameters
        if (body.view == "comparison") != has_comparison:
            raise ValidationFailedError("comparison dates must match the Profit and Loss view")
    if body.code in {"GSTR3B", "GSTR1"}:
        if body.code == "GSTR1":
            from reports.tasks.gstr1_catalog import context as gst_context
        else:
            from reports.tasks.gstr3b_catalog import context as gst_context

        parameters["_gst_context"] = gst_context(current.context.registrations, parameters)
    finance = current.context.finance
    if finance is None or not finance.company_active:
        raise ConflictError("current company financial configuration is required")
    presentation = current.context.report_display
    if presentation is None:
        raise ConflictError("current company report display configuration is required")
    if (
        presentation.base_currency != current.context.base_currency
        or presentation.amount_precision != finance.amount_precision
        or presentation.rounding_mode != finance.rounding_mode
    ):
        raise ConflictError("company report display configuration is inconsistent")

    async def check(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        resolve(current, body.code, body.version)
        if body.code == "GSTR1" and parameters.get("comparison_job_id"):
            from reports.domain.gstr3b import CALCULATION_VERSION as THREE_B_CALCULATION_VERSION

            compared = await get(
                db, company_id, ReportJob, uuid.UUID(parameters["comparison_job_id"])
            )
            authorize_job(current, compared)
            if (
                compared.status != "COMPLETE"
                or compared.definition["code"] != "GSTR3B"
                or compared.generation_id != body.generation_id
                or compared.parameters.get("registration_id") != parameters["registration_id"]
                or compared.parameters.get("period") != parameters["period"]
                or not compared.result
                or compared.result.get("evidence", {}).get("gstr3b", {}).get("calculation_version")
                != THREE_B_CALCULATION_VERSION
            ):
                raise ConflictError(
                    "select a completed GSTR-3B comparison for this GSTIN, period and source cut"
                )
        if origin is not None:
            parent = await get(db, company_id, ReportJob, origin.parent_id)
            authorize_job(current, parent)
            if (
                parent.kind != "RUN"
                or parent.status != "COMPLETE"
                or parent.attempt != origin.parent_attempt
                or parent.generation_id != body.generation_id
            ):
                raise ConflictError("completed drilldown parent is unavailable")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await jobs.admit(db)
        if body.code in {"GSTR3B", "GSTR1"}:
            from reports.models.gst_outward_review import GstOutwardReview
            from reports.models.gst_return_review import GstReturnReview

            review_model = GstOutwardReview if body.code == "GSTR1" else GstReturnReview
            from reports.tasks.common import company_lock

            await company_lock(db, current.actor.tenant_id, company_id)
            filed = await db.scalar(
                select(review_model.id).where(
                    review_model.company_id == company_id,
                    review_model.filed_period_key
                    == parameters["registration_id"] + ":" + parameters["period"],
                )
            )
            if filed:
                raise ConflictError(
                    "this return is externally filed; open its frozen preparation "
                    "or allocate a subsequent-period adjustment"
                )
        generation = await get(db, company_id, ReportGeneration, body.generation_id)
        if generation.status != "READY" or generation.manifest is None:
            raise ConflictError("select a reconciled source generation")
        try:
            manifest = Manifest.model_validate(generation.manifest)
        except ValidationError as exc:
            raise ConflictError("source generation schema is unavailable for new reports") from exc
        if body.code == "BALANCE_SHEET" and entry.definition.version >= 6:
            if manifest.control.coverage_start is None:
                raise ConflictError("Balance Sheet requires retained accounting history")
            history_start = manifest.control.coverage_start.isoformat()
            if any(
                parameters[key] < history_start
                for key in ("date_to", "comparative_to")
                if key in parameters
            ):
                raise ValidationFailedError(
                    "Balance Sheet dates precede available accounting history " + history_start
                )
        settings = request.app.state.settings
        native = await native_execution.enabled(db, settings, company_id, generation.id, body.code)
        if body.execution == "BULK" and not native:
            raise ConflictError("bulk calculation requires a verified native source")
        capacity = settings.source_fact_limit if native else settings.reference_fact_limit
        from reports.domain.reporting.inventory import CODES as INVENTORY_CODES
        from reports.tasks.analytics_catalog import CODES as ANALYTICS_CODES

        observed_count = (
            manifest.control.counts.get("inventory_report_record", 0)
            if body.code in INVENTORY_CODES
            else source_count(manifest)
        )
        if body.code in ANALYTICS_CODES:
            from reports.queries.native_context import NativeContext

            analytics_context = await NativeContext.load(db, company_id, generation.id)
            from reports.domain.analytics_common import periods as analytics_periods
            from reports.schemas.requests import RunRequest

            for _period, begin, end in analytics_periods(parameters):
                await analytics_context.validate(
                    db,
                    RunRequest.model_validate(
                        {
                            "code": "PROFIT_LOSS"
                            if body.code in {"PROFIT_MARGIN_ANALYSIS", "EXPENSE_PROFIT_LEAKAGE"}
                            else "ACCOUNT_SUMMARY",
                            "generation_id": generation.id,
                            "date_from": begin,
                            "date_to": end,
                        }
                    ),
                )
            capacity, observed_count = settings.native_result_limit, 0
        if body.code in {"GSTR3B", "GSTR1"}:
            capacity = settings.native_result_limit
            # The GST worker bounds each registration/period component before loading it.
            # Lifetime company counts are not the size of a statutory-period preparation.
            observed_count = 0
        if body.code in INVENTORY_CODES:
            capacity = settings.native_result_limit
            if not observed_count:
                raise ConflictError("complete inventory source coverage is unavailable")
            if (
                observed_count > capacity
                and body.code not in {"ITEM_LEDGER", "STOCK_MOVEMENT"}
                and not parameters.get("include_history")
                and not parameters.get("include_cost_details")
            ):
                from reports.tasks.inventory_source import balance_budget_count

                observed_count = await balance_budget_count(db, generation, capacity)
        if observed_count > capacity:
            raise ConflictError("generation exceeds the enabled reference plan capacity")
        definition = asdict(entry.definition)
        display = presentation.model_dump(mode="json")
        if origin is not None:
            display = (await get(db, company_id, ReportJob, origin.parent_id)).display
        row = ReportJob(
            tenant_id=current.actor.tenant_id,
            company_id=company_id,
            actor_id=current.actor.user_id,
            generation_id=body.generation_id,
            kind="RUN",
            lane="BULK"
            if body.execution == "BULK" or body.result_query is not None
            else ("SHORT" if native else entry.definition.resource_class),
            definition=definition,
            parameters=parameters,
            display=display,
            permission_hash=fingerprint(current),
            created_by=current.actor.user_id,
            origin=origin.model_dump(mode="json") if origin else None,
            options={
                "view": body.view,
                "execution": body.execution,
                "result_limit": settings.bulk_result_limit
                if body.execution == "BULK" or body.result_query is not None
                else (
                    settings.native_result_limit
                    if native or body.code in INVENTORY_CODES or body.code in ANALYTICS_CODES
                    else settings.reference_fact_limit
                ),
                **(
                    {"result_query": body.result_query.model_dump(mode="json")}
                    if body.result_query is not None
                    else {}
                ),
            },
            request_hash=hash_value(
                {
                    "definition": entry.definition.identity,
                    "generation": str(body.generation_id),
                    "parameters": parameters,
                    "permission": fingerprint(current),
                    "view": body.view,
                    "execution": body.execution,
                    "origin": origin.model_dump(mode="json") if origin else None,
                    "result_query": body.result_query.model_dump(mode="json")
                    if body.result_query
                    else None,
                }
            ),
        )
        db.add(row)
        await db.flush()
        jobs.dispatch(db, row)
        audit(db, row.tenant_id, company_id, row.id, "requested", row.actor_id)
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> JobDetail:
        row = await get(db, company_id, ReportJob, uuid.UUID(refs["id"]))
        authorize_job(current, row)
        return detail(row)

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            current.actor.tenant_id,
            company_id,
            current.actor.user_id,
            "reports.v2.run.create",
            idempotency_key,
            body.model_dump(mode="json")
            | {
                "parameters": parameters,
                "origin": origin.model_dump(mode="json") if origin else None,
            },
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
    return JSONResponse(result.value.model_dump(mode="json"), status_code=result.status)


@router.post("/report-runs", response_model=JobDetail, status_code=202)
async def create_run(
    company_id: uuid.UUID,
    body: FrameworkRunRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    return await submit_run(company_id, body, request, idempotency_key, current)


@router.post("/report-runs/{identity}/queries", response_model=JobDetail, status_code=202)
async def query_result(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    body: ResultQuery,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    from reports.domain.reporting.contracts import ReportDefinition
    from reports.domain.reporting.navigation import normalize

    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            parent = await get(db, company_id, ReportJob, identity)
            authorize_job(current, parent)
            if parent.kind != "RUN" or parent.status != "COMPLETE":
                raise ConflictError("completed query parent required")
            definition = ReportDefinition(
                **{**parent.definition, "views": tuple(detail(parent).views)}
            )
            query = normalize(definition, body)
            child = FrameworkRunRequest(
                code=parent.definition["code"],
                version=parent.definition["version"],
                generation_id=parent.generation_id,
                parameters=parent.parameters,
                view=(parent.options or {}).get("view", "default"),
                result_query=query,
            )
            origin = DrilldownOrigin(
                parent_id=parent.id,
                parent_attempt=parent.attempt,
                mapping="result_query",
            )
    return await submit_run(company_id, child, request, idempotency_key, current, origin)


def result_row(
    request: Request, current: Access, job: ReportJob, ordinal: int, data: dict[str, Any]
) -> ResultRow:
    from reports.domain.reporting.drilldowns import parameters_for

    links = []
    for mapping in job.definition.get("drilldowns", ()):
        if mapping["version"] != 1:
            continue
        if mapping["key"] == "stock_item_entries" and not (job.result or {}).get(
            "evidence", {}
        ).get("inventory_coverage", {}).get("movements_complete", False):
            continue
        try:
            resolve(current, mapping["target"])
        except (PermissionDeniedError, NotFoundError):
            continue
        parameters = parameters_for(
            mapping["key"],
            job.parameters,
            data,
            (job.result or {})
            .get("evidence", {})
            .get("inventory_coverage", {})
            .get("history_start")
            or (job.result or {})
            .get("owner_manifest", {})
            .get("control", {})
            .get("coverage_start"),
            retained_only=job.definition["code"]
            in {"PROFIT_MARGIN_ANALYSIS", "EXPENSE_PROFIT_LEAKAGE"},
        )
        if parameters is None:
            continue
        if mapping["key"] == "row_detail" and "_detail_cursor" in data:
            parameters = {"cursor": data["_detail_cursor"]}
        if mapping["key"] != "row_detail":
            try:
                resolve(current, mapping["target"]).handler.normalize(parameters)
            except ValidationError:
                continue
        token = codec(request, current, f"v2.drilldown:{job.id}:{job.attempt}").encode(
            {
                "mapping": mapping["key"],
                "ordinal": ordinal,
                "parameters": parameters,
            }
        )
        base = f"/v2/companies/{job.company_id}/report-runs/{job.id}"
        links.append(
            DrilldownLink(
                key=mapping["key"],
                title=mapping["title"],
                token=token,
                href=base + f"/rows/{ordinal}?token={token}"
                if mapping["key"] == "row_detail"
                else base + "/drilldowns",
                method="GET" if mapping["key"] == "row_detail" else "POST",
            )
        )
    return ResultRow(
        ordinal=ordinal,
        data={key: value for key, value in data.items() if not key.startswith("_")},
        source_ordinal=data.get("_source_ordinal"),
        drilldowns=tuple(links),
    )


@router.get("/report-runs/{identity}/rows/{ordinal}", response_model=ResultRow)
async def row_detail(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    ordinal: int,
    request: Request,
    current: Annotated[Access, Depends(access)],
    token: Annotated[str | None, Query(max_length=4096)] = None,
) -> ResultRow:
    from reports.queries.results import batches as result_batches

    if ordinal < 1:
        raise ValidationFailedError("row ordinal must be positive")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            job = await get(db, company_id, ReportJob, identity)
            authorize_job(current, job)
            if job.kind != "RUN" or job.status != "COMPLETE":
                raise ConflictError("completed report result required")
            selection = None
            if token is not None:
                selection = codec(request, current, f"v2.drilldown:{job.id}:{job.attempt}").decode(
                    token
                )
                if selection.get("mapping") != "row_detail" or selection.get("ordinal") != ordinal:
                    raise ValidationFailedError("row detail link differs from its selection")
            if (job.result or {}).get("plan", {}).get("mode") == "PINNED_QUERY":
                state = (selection or {}).get("parameters", {}).get("cursor")
                if state is not None:
                    if not isinstance(state, dict) or state.get("ordinal") != ordinal - 1:
                        raise ValidationFailedError(
                            "row detail position differs from its selection"
                        )
                    values, _next = await native_execution.rows(
                        db, job, 1, state, include_positions=True
                    )
                    if not values:
                        raise NotFoundError("report row not found")
                    return result_row(request, current, job, ordinal, values[0])
                if ordinal > 200:
                    raise ValidationFailedError("use the signed link for native row detail")
                count = 0
                async for values in result_batches(db, job):
                    if count < ordinal <= count + len(values):
                        return result_row(
                            request, current, job, ordinal, values[ordinal - count - 1]
                        )
                    count += len(values)
            else:
                total = (job.result or {}).get("row_count")
                if type(total) is not int or total < 0 or total != job.completed_rows:
                    raise ConflictError("retained result count evidence differs")
                if ordinal > total:
                    raise NotFoundError("report row not found")
                batch = await db.scalar(
                    select(ReportResultBatch).where(
                        ReportResultBatch.company_id == company_id,
                        ReportResultBatch.job_id == identity,
                        ReportResultBatch.attempt == job.attempt,
                        ReportResultBatch.first_ordinal <= ordinal,
                        ReportResultBatch.first_ordinal + ReportResultBatch.row_count > ordinal,
                    )
                )
                if batch is not None:
                    verify_batch(batch)
                    if batch.first_ordinal + batch.row_count - 1 > total:
                        raise ConflictError("retained result batch exceeds completed count")
                    return result_row(
                        request, current, job, ordinal, batch.rows[ordinal - batch.first_ordinal]
                    )
            raise NotFoundError("report row not found")


@router.get("/report-runs/{identity}", response_model=JobDetail)
async def run(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
) -> JobDetail:
    authorize(current)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            row = await get(db, company_id, ReportJob, identity)
            authorize_job(current, row)
            if row.kind != "RUN":
                raise ConflictError("report run required")
            return detail(row)


async def command(
    company: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Access,
    key: str,
    action: str,
    kind: str = "RUN",
) -> JSONResponse:
    async def check(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        row = await get(db, company, ReportJob, identity)
        authorize_job(current, row)
        if row.kind != kind:
            raise ConflictError("report command resource kind differs")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        if action == "retry":
            await jobs.retry(db, company, identity)
        else:
            row = await get(db, company, ReportJob, identity, lock=True)
            await jobs.cancel(db, row)
        return CommandReceipt(200, {"id": str(identity)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> JobDetail:
        return detail(await get(db, company, ReportJob, identity))

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            current.actor.tenant_id,
            company,
            current.actor.user_id,
            "reports.v2.job." + action,
            key,
            {"id": str(identity)},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
    return JSONResponse(result.value.model_dump(mode="json"), status_code=result.status)


@router.post("/report-runs/{identity}/cancel", response_model=JobDetail)
async def cancel(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    return await command(company_id, identity, request, current, idempotency_key, "cancel")


@router.post("/report-runs/{identity}/retry", response_model=JobDetail)
async def retry(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    idempotency_key: Idempotency,
    current: Annotated[Access, Depends(access)],
) -> JSONResponse:
    return await command(company_id, identity, request, current, idempotency_key, "retry")


@router.get("/report-runs/{identity}/rows", response_model=ResultPage)
async def rows(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> ResultPage:
    authorize(current)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            row = await get(db, company_id, ReportJob, identity)
            authorize_job(current, row)
            if row.kind != "RUN" or row.status != "COMPLETE":
                raise ConflictError("complete report result required")
            signer = codec(request, current, f"v2.rows:{identity}:{row.attempt}")
            if (row.result or {}).get("plan", {}).get("mode") == "PINNED_QUERY":
                state = None if cursor is None else signer.decode(cursor)
                values, next_state = await native_execution.rows(
                    db, row, limit, state, include_positions=True
                )
                ordinal = 0 if state is None else state["ordinal"]
                return ResultPage(
                    items=[
                        result_row(request, current, row, ordinal + index, value)
                        for index, value in enumerate(values, 1)
                    ],
                    page=PageMeta(
                        limit=limit,
                        has_more=next_state is not None,
                        next_cursor=signer.encode(next_state) if next_state else None,
                    ),
                )
            after = 0 if cursor is None else signer.decode(cursor).get("after")
            if type(after) is not int or after < 0:
                raise ValidationFailedError("invalid result cursor")
            total = (row.result or {}).get("row_count")
            if type(total) is not int or total < 0 or total != row.completed_rows:
                raise ConflictError("retained result count evidence differs")
            if after > total:
                raise ValidationFailedError("result cursor exceeds retained result")
            batches = await db.scalars(
                select(ReportResultBatch)
                .where(
                    ReportResultBatch.company_id == company_id,
                    ReportResultBatch.job_id == identity,
                    ReportResultBatch.attempt == row.attempt,
                    ReportResultBatch.first_ordinal <= after + limit + 1,
                    ReportResultBatch.first_ordinal + ReportResultBatch.row_count > after + 1,
                )
                .order_by(ReportResultBatch.first_ordinal)
                .limit(201)
            )
            verified = list(batches)
            for batch in verified:
                verify_batch(batch)
                if batch.first_ordinal + batch.row_count - 1 > total:
                    raise ConflictError("retained result batch exceeds completed count")
            items = [
                result_row(request, current, row, batch.first_ordinal + index, value)
                for batch in verified
                for index, value in enumerate(batch.rows)
                if after < batch.first_ordinal + index <= after + limit + 1
            ]
            if [item.ordinal for item in items] != list(
                range(after + 1, min(total, after + limit + 1) + 1)
            ):
                raise ConflictError("retained result page has missing or repeated rows")
            more = len(items) > limit
            selected = items[:limit]
            token = signer.encode({"after": selected[-1].ordinal}) if more else None
            return ResultPage(
                items=selected, page=PageMeta(limit=limit, has_more=more, next_cursor=token)
            )
