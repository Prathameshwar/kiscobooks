"""Company-scoped asynchronous generation/run entry and protected frozen reads."""

import uuid
from typing import Annotated, Any

from billing_platform.db import tenant_scope
from billing_platform.errors import (
    ConflictError,
    ErrorEnvelope,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.ids import uuid7
from billing_platform.listing import PageMeta
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from reporting_contract.contract import Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.api.auth import Access, access
from reports.domain.reconcile import RULE_HASH
from reports.domain.statements import CODES, RULE_VERSIONS, RULES, STATEMENTS
from reports.models import core as m
from reports.models.source_versions import ReportSourceCut
from reports.schemas.requests import (
    Definition,
    GenerationDetail,
    GenerationRequest,
    ListItem,
    ResourcePage,
    RowItem,
    RowPage,
    RunDetail,
    RunRequest,
)
from reports.tasks.access import authorize, fingerprint
from reports.tasks.common import audit, company_lock, get
from reports.tasks.reference_source import LEGACY_FACT_LIMIT, source_count
from reports.tasks.runs import definition

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 500)},
)
Idempotency = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=120)]


def generation_detail(row: m.ReportGeneration) -> GenerationDetail:
    return GenerationDetail.model_validate(
        {key: getattr(row, key) for key in GenerationDetail.model_fields}
    )


def codec(request: Request, current: Access, purpose: str, ttl: int = 900) -> CursorCodec:
    return CursorCodec(
        request.app.state.settings.artifact_signing_secret.get_secret_value().encode(),
        context=fingerprint(current) + ":" + purpose,
        ttl_seconds=ttl,
    )


def bank_evidence_fields(current: Access) -> None:
    """A report includes source columns; deny the export if any source read is denied."""
    sensitive = {
        "bank_statement_import",
        "bank_statement_entry",
        "bank_match_event",
        "bank_opening_item",
        "bank_reconciliation_session",
        "bank_adjustment_proposal",
        "bank_instrument",
        "journal_line",
    }
    if any(
        policy.get("access") == "read"
        and policy.get("effect") == "deny"
        and str(policy.get("entity_type", "")).removeprefix("accounting.") in sensitive
        for policy in current.context.policies
    ):
        raise PermissionDeniedError("bank evidence report contains protected source fields")


async def run_detail(
    db: AsyncSession, request: Request, current: Access, row: m.ReportRun
) -> RunDetail:
    if row.parameters.get("code") in {
        "BANK_RECONCILIATION",
        "BANK_RECONCILIATION_EVIDENCE",
        "BANK_RECONCILIATION_WORKLIST",
        "PAYMENT_REGISTER",
        "RECEIPT_REGISTER",
    }:
        from billing_platform.authz import ScopePath

        current.actor.require_scope(
            "accounting.bank.read", target=ScopePath(company_id=row.company_id)
        )
        if row.parameters.get("code") in {
            "BANK_RECONCILIATION_EVIDENCE",
            "BANK_RECONCILIATION_WORKLIST",
        }:
            bank_evidence_fields(current)
            current.actor.require_scope(
                "accounting.statement.read", target=ScopePath(company_id=row.company_id)
            )
    if row.permission_hash != fingerprint(current):
        raise PermissionDeniedError("report disclosure scope changed")
    token = None
    if row.status == "COMPLETE":
        artifact = await db.scalar(
            select(m.ReportArtifact).where(
                m.ReportArtifact.company_id == row.company_id, m.ReportArtifact.run_id == row.id
            )
        )
        if artifact:
            token = codec(request, current, "download:" + str(row.id), 120).encode(
                {"hash": artifact.content_hash}
            )
    return RunDetail(
        id=row.id,
        generation_id=row.generation_id,
        status=row.status,
        evidence=row.evidence,
        failure_code=row.failure_code,
        download_token=token,
    )


@router.get("/report-definitions", response_model=list[Definition])
async def definitions(company_id: uuid.UUID, current: Access = Depends(access)) -> list[Definition]:
    authorize(current)
    return [Definition(code="SOURCE_RECONCILIATION", version=1, rule_hash=RULE_HASH)] + [
        Definition(
            code=code,
            version=RULE_VERSIONS[code],
            rule_hash=RULES[code],
            financial_statement=code in STATEMENTS,
        )
        for code in CODES
    ]


@router.post("/report-generations", response_model=GenerationDetail, status_code=202)
async def create_generation(
    company_id: uuid.UUID,
    body: GenerationRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def check(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        authorize(current, "report.definition.manage")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await company_lock(db, current.actor.tenant_id, company_id)
        row = m.ReportGeneration(
            tenant_id=current.actor.tenant_id,
            company_id=company_id,
            snapshot_id=uuid7(),
            created_by=current.actor.user_id,
        )
        db.add(row)
        await db.flush()
        audit(db, current.actor.tenant_id, company_id, row.id, "requested", current.actor.user_id)
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> GenerationDetail:
        return generation_detail(
            await get(db, company_id, m.ReportGeneration, uuid.UUID(refs["id"]))
        )

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            current.actor.tenant_id,
            company_id,
            current.actor.user_id,
            "reports.generation.create",
            idempotency_key,
            body.model_dump(mode="json"),
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
    return JSONResponse(result.value.model_dump(mode="json"), status_code=result.status)


@router.get("/report-generations/{identity}", response_model=GenerationDetail)
async def generation(
    company_id: uuid.UUID, identity: uuid.UUID, request: Request, current: Access = Depends(access)
) -> GenerationDetail:
    authorize(current)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            return generation_detail(await get(db, company_id, m.ReportGeneration, identity))


@router.post("/report-runs", response_model=RunDetail, status_code=202)
async def create_run(
    company_id: uuid.UUID,
    body: RunRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def check(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        authorize(current)
        if body.code in {
            "BANK_RECONCILIATION",
            "BANK_RECONCILIATION_EVIDENCE",
            "BANK_RECONCILIATION_WORKLIST",
            "PAYMENT_REGISTER",
            "RECEIPT_REGISTER",
        }:
            from billing_platform.authz import ScopePath

            current.actor.require_scope(
                "accounting.bank.read", target=ScopePath(company_id=company_id)
            )
            if body.code in {"BANK_RECONCILIATION_EVIDENCE", "BANK_RECONCILIATION_WORKLIST"}:
                bank_evidence_fields(current)
                current.actor.require_scope(
                    "accounting.statement.read", target=ScopePath(company_id=company_id)
                )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await company_lock(db, current.actor.tenant_id, company_id)
        selected = await get(db, company_id, m.ReportGeneration, body.generation_id)
        if selected.status != "READY" or selected.manifest is None:
            raise ConflictError("select a reconciled generation")
        versioned = await db.scalar(
            select(ReportSourceCut.id).where(
                ReportSourceCut.company_id == company_id,
                ReportSourceCut.generation_id == selected.id,
            )
        )
        if versioned is not None:
            try:
                size = source_count(Manifest.model_validate(selected.manifest))
            except ValueError as exc:
                raise ConflictError("versioned source schema is unavailable") from exc
            if size > LEGACY_FACT_LIMIT:
                raise ConflictError("generation exceeds the legacy report capacity; use v2 reports")
        defined = await definition(db, current.actor.tenant_id, company_id, body.code)
        row = m.ReportRun(
            tenant_id=current.actor.tenant_id,
            company_id=company_id,
            generation_id=selected.id,
            definition_id=defined.id,
            permission_hash=fingerprint(current),
            parameters=body.model_dump(mode="json"),
            created_by=current.actor.user_id,
        )
        db.add(row)
        await db.flush()
        audit(db, current.actor.tenant_id, company_id, row.id, "requested", current.actor.user_id)
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> RunDetail:
        return await run_detail(
            db, request, current, await get(db, company_id, m.ReportRun, uuid.UUID(refs["id"]))
        )

    result = await execute_idempotent(
        request.app.state.session_factory,
        CommandIdentity(
            current.actor.tenant_id,
            company_id,
            current.actor.user_id,
            "reports.run.create",
            idempotency_key,
            body.model_dump(mode="json"),
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
    return JSONResponse(result.value.model_dump(mode="json"), status_code=result.status)


@router.get("/report-runs/{identity}", response_model=RunDetail)
async def run(
    company_id: uuid.UUID, identity: uuid.UUID, request: Request, current: Access = Depends(access)
) -> RunDetail:
    authorize(current)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            return await run_detail(
                db, request, current, await get(db, company_id, m.ReportRun, identity)
            )


@router.get("/report-runs/{identity}/rows", response_model=RowPage)
async def rows(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=4096),
    current: Access = Depends(access),
) -> RowPage:
    authorize(current)
    paging = codec(request, current, "rows:" + str(identity) + ":" + str(limit))
    after = paging.decode(cursor)["ordinal"] if cursor else 0
    if type(after) is not int or after < 0:
        raise ValidationFailedError("invalid report cursor")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            selected = await get(db, company_id, m.ReportRun, identity)
            await run_detail(db, request, current, selected)
            if selected.status != "COMPLETE":
                raise ConflictError("report output is not complete")
            records = list(
                await db.scalars(
                    select(m.ReportRow)
                    .where(
                        m.ReportRow.company_id == company_id,
                        m.ReportRow.run_id == identity,
                        m.ReportRow.ordinal > after,
                    )
                    .order_by(m.ReportRow.ordinal)
                    .limit(limit + 1)
                )
            )
            more = len(records) > limit
            items = records[:limit]
            return RowPage(
                items=[RowItem(id=row.id, ordinal=row.ordinal, data=row.data) for row in items],
                page=PageMeta(
                    limit=limit,
                    has_more=more,
                    next_cursor=paging.encode({"ordinal": items[-1].ordinal}) if more else None,
                ),
            )


@router.get("/report-runs/{identity}/download")
async def download(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    token: str = Query(max_length=4096),
    current: Access = Depends(access),
) -> Response:
    authorize(current, "report.export")
    allowed = codec(request, current, "download:" + str(identity), 120).decode(token)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            selected = await get(db, company_id, m.ReportRun, identity)
            await run_detail(db, request, current, selected)
            artifact = await db.scalar(
                select(m.ReportArtifact).where(
                    m.ReportArtifact.company_id == company_id, m.ReportArtifact.run_id == identity
                )
            )
            if (
                artifact is None
                or selected.status != "COMPLETE"
                or allowed.get("hash") != artifact.content_hash
            ):
                raise PermissionDeniedError("report artifact is unavailable")
            audit(
                db, current.actor.tenant_id, company_id, identity, "exported", current.actor.user_id
            )
            content = artifact.body
    return Response(
        content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=report.csv",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/report-definitions/{code}/field-set")
async def field_set(
    company_id: uuid.UUID, code: str, current: Access = Depends(access)
) -> dict[str, Any]:
    authorize(current)
    if code not in {"SOURCE_RECONCILIATION", *CODES}:
        raise ValidationFailedError("unsupported report definition")
    from reports.domain.invoice_registers import CODES as INVOICE_CODES

    native = RunRequest.model_json_schema()
    fields = native["properties"]
    if code not in INVOICE_CODES:
        for key in ("invoice_id", "date_basis", "company_registration_id"):
            fields.pop(key)
    else:
        date_bases = ["POSTING"]
        if code in {"SALES_REGISTER", "PURCHASE_REGISTER", "INVOICE_TAX_REGISTER"}:
            date_bases.append("DOCUMENT")
        if code in {"INVOICE_TAX_REGISTER", "TAX_GL_BRIDGE"}:
            date_bases.append("TAX_POINT")
        fields["date_basis"]["enum"] = date_bases
        if code not in {"INVOICE_TAX_REGISTER", "INVOICE_CREDIT_REGISTER", "TAX_GL_BRIDGE"}:
            fields.pop("company_registration_id")
    return {
        "native": native,
        "rule_hash": RULE_HASH if code == "SOURCE_RECONCILIATION" else RULES[code],
        "complete_input_required": True,
        "formats": ["CSV"],
    }


async def listing(
    request: Request, current: Access, kind: str, limit: int, cursor: str | None
) -> ResourcePage:
    authorize(current)
    if set(request.query_params) - {"limit", "cursor"} or len(request.query_params) != len(
        request.query_params.multi_items()
    ):
        raise ValidationFailedError("unsupported report list query")
    paging = codec(request, current, "list:" + kind + ":" + str(limit))
    after = paging.decode(cursor).get("id") if cursor else None
    try:
        identity = uuid.UUID(after) if after else None
    except (ValueError, TypeError) as exc:
        raise ValidationFailedError("invalid report cursor") from exc
    model = m.ReportRun if kind == "runs" else m.ReportGeneration
    position = m.ReportRun.generation_id if kind == "runs" else m.ReportGeneration.applied_sequence
    query = select(model.id, model.status, position.label("position")).where(
        model.company_id == current.context.company_id
    )
    if kind == "runs":
        query = query.where(m.ReportRun.permission_hash == fingerprint(current))
    if identity:
        query = query.where(model.id > identity)
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            records = list((await db.execute(query.order_by(model.id).limit(limit + 1))).all())
            selected = records[:limit]
            more = len(records) > limit
            return ResourcePage(
                items=[
                    ListItem(
                        id=row.id,
                        status=row.status,
                        generation_id=row.position if kind == "runs" else None,
                        applied_sequence=row.position if kind == "generations" else None,
                    )
                    for row in selected
                ],
                page=PageMeta(
                    limit=limit,
                    has_more=more,
                    next_cursor=paging.encode({"id": str(selected[-1].id)}) if more else None,
                ),
            )


@router.get("/report-generations", response_model=ResourcePage)
async def generations(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=4096),
    current: Access = Depends(access),
) -> ResourcePage:
    return await listing(request, current, "generations", limit, cursor)


@router.get("/report-runs", response_model=ResourcePage)
async def report_runs(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=4096),
    current: Access = Depends(access),
) -> ResourcePage:
    return await listing(request, current, "runs", limit, cursor)
