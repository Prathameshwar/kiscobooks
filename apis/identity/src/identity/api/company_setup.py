"""Read and retry one company's durable setup under current object authority."""

import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import lock_tenant
from identity.models.company import Company
from identity.models.company_setup import CompanySetupRun, CompanySetupStep, ReportSourceEnrollment
from identity.schemas.base import StrictModel
from identity.schemas.company_setup import CompanySetupStatus, SetupStepView
from identity.services.audit import record

router = APIRouter(
    prefix="/v1/companies/{company_id}/setup", route_class=StrictRoute, responses=ERROR_RESPONSES
)
commands_router = APIRouter(
    prefix="/v1/company-setup-commands", route_class=StrictRoute, responses=ERROR_RESPONSES
)


class CreationReceipt(StrictModel):
    company_id: uuid.UUID


@commands_router.get("/{key}", response_model=CreationReceipt)
async def creation_receipt(
    key: str, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> CreationReceipt:
    from identity.services.company_setup import command_key

    current.require("company.read")
    row = await db.scalar(
        select(CompanySetupRun).where(CompanySetupRun.command_key == command_key(current, key))
    )
    if row is None:
        raise NotFoundError("company creation has not completed")
    current.require_scope("company.read", target=ScopePath(company_id=row.company_id))
    return CreationReceipt(company_id=row.company_id)


async def load(db: AsyncSession, current: Actor, company: uuid.UUID) -> CompanySetupRun:
    current.require_scope("company.read", target=ScopePath(company_id=company))
    row = await db.scalar(select(CompanySetupRun).where(CompanySetupRun.company_id == company))
    if row is None:
        raise NotFoundError("company setup is not enrolled")
    return row


async def detail(db: AsyncSession, row: CompanySetupRun) -> CompanySetupStatus:
    steps = list(
        await db.scalars(
            select(CompanySetupStep)
            .where(CompanySetupStep.company_id == row.company_id)
            .order_by(CompanySetupStep.id)
        )
    )
    return CompanySetupStatus(
        id=row.id,
        company_id=row.company_id,
        status=row.status,
        opening_choice=row.opening_choice,
        failure_code=row.failure_code,
        updated_at=row.updated_at,
        steps=[SetupStepView.model_validate(step) for step in steps],
    )


@router.get("", response_model=CompanySetupStatus)
async def read(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> CompanySetupStatus:
    return await detail(db, await load(db, current, company_id))


@router.post("/retry", response_model=CompanySetupStatus)
async def retry(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> CompanySetupStatus:
    await lock_tenant(db, current.tenant_id)
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    row = await load(db, current, company_id)
    company = await db.get(Company, company_id)
    if company is None or company.status != "active":
        raise ConflictError("company is unavailable for setup")
    if row.status in {"RETRY_WAIT", "NEEDS_ACTION"}:
        # Retry never changes the original declaration or its initiating actor.
        row.status, row.failure_code, row.available_at = "PENDING", None, utcnow()
        row.updated_by = current.user_id
        record(
            db,
            current,
            action="company.setup_retried",
            entity="company_setup_run",
            entity_id=row.id,
            company_id=company_id,
            changes={"status": {"to": "PENDING"}},
        )
    return await detail(db, row)


class ReportEnrollmentStatus(StrictModel):
    company_id: uuid.UUID
    enrolled: bool


@router.post("/enroll-reports", response_model=ReportEnrollmentStatus)
async def enroll_existing_reports(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> ReportEnrollmentStatus:
    """Audited adoption preserves existing books, openings, periods and report history."""
    from billing_platform.ids import uuid7

    await lock_tenant(db, current.tenant_id)
    for permission in ("company.update", "report.definition.manage"):
        current.require_scope(permission, target=ScopePath(company_id=company_id))
    company = await db.get(Company, company_id)
    if company is None:
        raise NotFoundError("company not found")
    if company.status != "active":
        raise ConflictError("only an active company can start automatic collection")
    row = await db.scalar(
        select(ReportSourceEnrollment).where(ReportSourceEnrollment.company_id == company_id)
    )
    if row is None:
        row = ReportSourceEnrollment(
            id=uuid7(),
            tenant_id=current.tenant_id,
            company_id=company_id,
            status="ACTIVE",
            revision=1,
            created_by=current.user_id,
            updated_by=current.user_id,
        )
        db.add(row)
        record(
            db,
            current,
            action="report_source.enrolled",
            entity="report_source_enrollment",
            entity_id=row.id,
            company_id=company_id,
            changes={"status": {"to": "ACTIVE"}},
        )
    return ReportEnrollmentStatus(company_id=company_id, enrolled=row.status == "ACTIVE")
