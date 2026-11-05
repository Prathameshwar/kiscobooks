"""Fiscal controls and protected calendar reads."""

import uuid
from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import NotFoundError, PermissionDeniedError
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import (
    ERROR_RESPONSES,
    Idempotency,
    no_query,
    response,
    session,
    unique_query,
)
from accounting.financial_resources import FINANCIAL_BY_NAME, FINANCIAL_BY_PATH
from accounting.models.fiscal import FinancialSetup
from accounting.schemas.fiscal import (
    FinancialSettingChange,
    FinancialSetupDetail,
    FinancialSetupReconcile,
    FinancialSetupReview,
    FiscalPeriodDetail,
    FiscalPeriodListItem,
    FiscalQuery,
    FiscalReadiness,
    FiscalYearDetail,
    FiscalYearGenerate,
    FiscalYearListItem,
    NextYearPreview,
    NextYearQuery,
    PeriodTransition,
)
from accounting.schemas.masters import Input
from accounting.schemas.query import FieldSet
from accounting.tasks import fiscal
from accounting.tasks.access import authorize, readable
from accounting.tasks.commands import protected, values_of
from accounting.tasks.reads import field_set, listing


async def financial_rate(request: Request, current: Access = Depends(access)) -> None:
    key = f"finance:{current.actor.tenant_id}:{current.context.company_id}:{current.actor.user_id}"
    if not request.app.state.write_limiter.allow(key, limit=120):
        raise HTTPException(status_code=429)


router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post(
    "/financial-setup/initialize",
    response_model=FinancialSetupDetail,
    dependencies=[Depends(financial_rate)],
)
async def initialize(
    company_id: uuid.UUID,
    body: Input,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await fiscal.initialize(request.app.state.session_factory, current, idempotency_key),
    )


@router.get(
    "/financial-setup", response_model=FinancialSetupDetail, response_model_exclude_unset=True
)
async def get_setup(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = FINANCIAL_BY_NAME["financial_setup"]
    authorize(current, spec, "read")
    row = await db.scalar(select(FinancialSetup).where(FinancialSetup.company_id == company_id))
    if row is None:
        raise NotFoundError("financial setup not found")
    return protected(row, spec, current)


@router.post(
    "/financial-setup/reconcile",
    response_model=FinancialSetupDetail,
    dependencies=[Depends(financial_rate)],
)
async def reconcile(
    company_id: uuid.UUID,
    body: FinancialSetupReconcile,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    from accounting.tasks.fiscal_reconciliation import reconcile as apply

    no_query(request)
    return response(
        request, await apply(request.app.state.session_factory, current, body, idempotency_key)
    )


@router.get("/financial-setup/reconciliation-review", response_model=FinancialSetupReview)
async def reconciliation_review(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> FinancialSetupReview:
    """Review current signed facts; this read never changes books or bypasses repair guards."""
    no_query(request)
    spec = FINANCIAL_BY_NAME["financial_setup"]
    authorize(current, spec, "read")
    current.actor.require_scope(
        "accounting.finance.manage", target=ScopePath(company_id=company_id)
    )
    row = await db.scalar(select(FinancialSetup).where(FinancialSetup.company_id == company_id))
    if row is None:
        raise NotFoundError("financial setup not found")
    before = values_of(row, spec)
    target = fiscal.snapshot(current)
    if not set(target) <= (
        readable(current, spec, before) & readable(current, spec, before | target)
    ):
        raise PermissionDeniedError("financial settings must be readable before reconciliation")
    return FinancialSetupReview(
        expected_version=row.row_version,
        configuration_hash=str(target["configuration_hash"]),
        changes=[
            FinancialSettingChange(field=key, before=str(before[key]), after=str(value))
            for key, value in target.items()
            if before[key] != value
        ],
    )


@router.get("/finance/field-sets/{resource}", response_model=FieldSet)
async def fields(
    company_id: uuid.UUID, resource: str, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    spec = FINANCIAL_BY_PATH.get(resource)
    if spec is None:
        raise NotFoundError("financial resource not found")
    return field_set(current, spec)


@router.post(
    "/fiscal-years/generate",
    response_model=FiscalYearDetail,
    dependencies=[Depends(financial_rate)],
)
async def generate(
    company_id: uuid.UUID,
    body: FiscalYearGenerate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await fiscal.generate(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.get(
    "/fiscal-years",
    response_model=Page[FiscalYearListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def years(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[FiscalQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        FINANCIAL_BY_NAME["fiscal_year"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        FiscalYearListItem,
    )


@router.get(
    "/fiscal-years/next-preview",
    response_model=NextYearPreview,
    dependencies=[Depends(unique_query)],
)
async def next_year_preview(
    company_id: uuid.UUID,
    query: Annotated[NextYearQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, object]:
    from accounting.tasks.next_fiscal_year import preview

    return await preview(db, current, query.source_year_id)


@router.get(
    "/fiscal-years/{object_id}", response_model=FiscalYearDetail, response_model_exclude_unset=True
)
async def year(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = FINANCIAL_BY_NAME["fiscal_year"]
    authorize(current, spec, "read")
    return protected(
        await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/fiscal-periods",
    response_model=Page[FiscalPeriodListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def periods(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[FiscalQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        FINANCIAL_BY_NAME["fiscal_period"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        FiscalPeriodListItem,
    )


@router.get(
    "/fiscal-periods/{object_id}",
    response_model=FiscalPeriodDetail,
    response_model_exclude_unset=True,
)
async def period(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = FINANCIAL_BY_NAME["fiscal_period"]
    authorize(current, spec, "read")
    return protected(
        await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/fiscal-periods/{object_id}/transition",
    response_model=FiscalPeriodDetail,
    dependencies=[Depends(financial_rate)],
)
async def transition(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PeriodTransition,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await fiscal.transition(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


# Fiscal exports use the same scoped/field-protected cursor mechanism as journal exports.
def add_export(name: str) -> None:
    spec = FINANCIAL_BY_NAME[name]

    async def export(
        company_id: uuid.UUID,
        request: Request,
        query: Annotated[FiscalQuery, Query()],
        current: Access = Depends(access),
        db: AsyncSession = Depends(session),
    ) -> JSONResponse:
        from accounting.api.workflows import export_records

        return await export_records(company_id, spec.path, request, query, current, db)

    router.add_api_route(
        "/exports/" + spec.path,
        export,
        methods=["GET"],
        response_model=Page.__class_getitem__(spec.detail),
        response_model_exclude_unset=True,
        dependencies=[Depends(unique_query)],
        name="export_" + name,
    )


for resource_name in ("financial_setup", "fiscal_year", "fiscal_period"):
    add_export(resource_name)


@router.get("/fiscal-years/{object_id}/readiness", response_model=FiscalReadiness)
async def readiness(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, object]:
    from accounting.tasks.fiscal_readiness import readiness as assess

    return await assess(db, current, object_id)
