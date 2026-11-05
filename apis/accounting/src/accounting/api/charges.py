"""Overdue policy, calculation and separate approval endpoints."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, Idempotency, no_query, response, session
from accounting.api.fiscal import financial_rate
from accounting.api.subledger import add_reads
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.schemas import charges as schema
from accounting.schemas.charge_tax import (
    ChargeTaxSnapshotDetail,
    ChargeTaxSnapshotListItem,
    TaxEvidence,
)
from accounting.tasks import charge_calculation, charge_policies, charge_tax, charges

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post(
    "/charge-policies",
    response_model=schema.ChargePolicyDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def policy(
    company_id: uuid.UUID,
    body: schema.ChargePolicyCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charge_policies.create(
            request.app.state.session_factory, current, body, idempotency_key
        ),
    )


@router.post(
    "/charge-policies/{object_id}/close",
    response_model=schema.ChargePolicyDetail,
    dependencies=[Depends(financial_rate)],
)
async def close(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.ChargePolicyClose,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charge_policies.close(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post("/charge-assessments/preview", response_model=schema.ChargePreview)
async def preview(
    company_id: uuid.UUID,
    body: schema.ChargeRequest,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> schema.ChargePreview:
    no_query(request)
    return await charge_calculation.preview(db, current, body)


@router.post(
    "/charge-assessments",
    response_model=schema.ChargeAssessmentDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def create(
    company_id: uuid.UUID,
    body: schema.ChargeRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charges.create(request.app.state.session_factory, current, body, idempotency_key),
    )


@router.post(
    "/charge-assessments/{object_id}/approve",
    response_model=schema.ChargeAssessmentDetail,
    dependencies=[Depends(financial_rate)],
)
async def approve(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.ChargeApprove,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charges.approve(
            request.app.state.session_factory, current, object_id, body, idempotency_key
        ),
    )


@router.post(
    "/charge-assessments/{object_id}/waive",
    response_model=schema.ChargeAssessmentDetail,
    dependencies=[Depends(financial_rate)],
)
async def waive(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.ChargeApprove,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charges.dispose(
            request.app.state.session_factory, current, object_id, body, idempotency_key, waive=True
        ),
    )


@router.post(
    "/charge-assessments/{object_id}/reject",
    response_model=schema.ChargeAssessmentDetail,
    dependencies=[Depends(financial_rate)],
)
async def reject(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schema.ChargeApprove,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charges.dispose(
            request.app.state.session_factory,
            current,
            object_id,
            body,
            idempotency_key,
            waive=False,
        ),
    )


add_reads(FINANCIAL_BY_NAME["charge_policy"], schema.ChargePolicyListItem, target=router)
add_reads(FINANCIAL_BY_NAME["charge_assessment"], schema.ChargeAssessmentListItem, target=router)


@router.post(
    "/charge-tax-snapshots",
    response_model=ChargeTaxSnapshotDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def tax_evidence(
    company_id: uuid.UUID,
    body: TaxEvidence,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await charge_tax.ingest(
            request.app.state.session_factory,
            current,
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


add_reads(FINANCIAL_BY_NAME["charge_tax_snapshot"], ChargeTaxSnapshotListItem, target=router)
