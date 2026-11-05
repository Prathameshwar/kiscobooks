"""Versioned framework API; permissions are checked on every discovery and read."""

from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.errors import (
    ErrorEnvelope,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError

from reports.api.auth import Access, access
from reports.domain.reporting.contracts import fingerprint
from reports.domain.reporting.registry import Registration
from reports.schemas.framework import (
    DefinitionCatalog,
    DefinitionDetail,
    DefinitionFields,
    ParameterValidation,
    ValidatedParameters,
)
from reports.tasks.access import authorize, can_prepare_gst
from reports.tasks.report_catalog import ReferenceAdapter, catalog

router = APIRouter(
    prefix="/v2/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 500)},
)


def resolve(
    current: Access, code: str, version: int | None = None
) -> Registration[ReferenceAdapter]:
    authorize(current)
    if code in {"GSTR3B", "GSTR1"}:
        from reports.domain.gstr1_rules import applicable

        if not any(applicable(row) for row in current.context.registrations):
            raise PermissionDeniedError("GSTR-3B requires an eligible Indian GST registration")
    try:
        entry = catalog().resolve(code, version)
    except KeyError:
        raise NotFoundError("report definition not found") from None
    for permission in entry.definition.permissions:
        current.actor.require_scope(
            permission, target=ScopePath(company_id=current.context.company_id)
        )
    return entry


def detail(
    entry: Registration[ReferenceAdapter], request: Request, current: Access
) -> DefinitionDetail:
    from reports.rendering.capabilities import available

    if not hasattr(request.state, "report_export_limits"):
        try:
            authorize(current, "report.export")
            request.state.report_export_limits = available(request.app.state.settings)
        except PermissionDeniedError:
            request.state.report_export_limits = ()
    limits = request.state.report_export_limits
    if entry.definition.code in {"GSTR3B", "GSTR1"}:
        limits = tuple(item for item in limits if item.format in {"PDF", "XLSX", "CSV"})
    settings = request.app.state.settings
    from reports.domain.reporting.inventory import CODES as INVENTORY_CODES
    from reports.domain.reporting.navigation import capabilities

    return DefinitionDetail(
        definition=entry.definition,
        parameter_schema=entry.handler.parameters(),
        run_enabled=request.app.state.settings.framework_enabled
        and (entry.definition.code not in {"GSTR3B", "GSTR1"} or can_prepare_gst(current)),
        formats=tuple(item.format for item in limits),
        export_limits=limits,
        execution_limits={
            "STANDARD": (
                settings.native_result_limit
                if entry.definition.code in INVENTORY_CODES
                else settings.source_fact_limit * 2
                if entry.definition.code
                in {"ACCOUNT_LEDGER", "DAY_BOOK", "PARTY_LEDGER", "CASH_BOOK", "BANK_BOOK"}
                else settings.native_result_limit
            )
            if settings.native_queries_enabled
            else (
                settings.native_result_limit
                if entry.definition.code in INVENTORY_CODES
                else settings.reference_fact_limit
            ),
            **(
                {"BULK": settings.bulk_result_limit}
                if settings.native_queries_enabled and entry.definition.code == "ACCOUNT_SUMMARY"
                else {}
            ),
        },
        package_limits={
            "max_parts": settings.package_max_parts,
            "max_rows": settings.export_max_rows,
            "max_bytes": settings.export_max_bytes,
            "timeout_seconds": settings.export_timeout_seconds,
            "pdf_part_rows": 1000,
            "html_part_rows": 10000,
        }
        if limits
        else {},
        navigation=capabilities(entry.definition),
    )


@router.get("/report-definitions", response_model=DefinitionCatalog)
async def definitions(
    request: Request, current: Annotated[Access, Depends(access)]
) -> DefinitionCatalog:
    authorize(current)
    permitted = []
    for code, version in sorted(catalog().reports):
        if version != catalog().resolve(code).definition.version:
            continue
        try:
            entry = resolve(current, code, version)
        except PermissionDeniedError:
            continue
        permitted.append(detail(entry, request, current))
    return DefinitionCatalog(items=tuple(permitted))


@router.get("/report-definitions/{code}", response_model=DefinitionDetail)
async def definition(
    code: str,
    request: Request,
    current: Annotated[Access, Depends(access)],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> DefinitionDetail:
    return detail(resolve(current, code, version), request, current)


@router.get("/report-definitions/{code}/field-set", response_model=DefinitionFields)
async def field_set(
    code: str,
    request: Request,
    current: Annotated[Access, Depends(access)],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> DefinitionFields:
    item = detail(resolve(current, code, version), request, current)
    return DefinitionFields(
        code=item.definition.code,
        version=item.definition.version,
        native=item.parameter_schema,
        views=item.definition.views,
        formats=item.formats,
        export_limits=item.export_limits,
        execution_limits=item.execution_limits,
        package_limits=item.package_limits,
        navigation=item.navigation,
    )


@router.post("/report-definitions/{code}/validate", response_model=ValidatedParameters)
async def validate_parameters(
    code: str,
    body: ParameterValidation,
    current: Annotated[Access, Depends(access)],
) -> ValidatedParameters:
    entry = resolve(current, code, body.version)
    try:
        parameters = entry.handler.normalize(body.parameters)
    except ValidationError:
        raise ValidationFailedError("parameters do not match the report definition") from None
    return ValidatedParameters(
        code=code,
        version=entry.definition.version,
        parameters=parameters,
        parameter_hash=fingerprint(parameters),
        definition_identity=entry.definition.identity,
    )
