"""Masked bank resources; plaintext is available only through a fresh, audited reveal."""

from __future__ import annotations

import time
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.reference_models import Currency
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.children import contact_company
from identity.api.dependencies import session
from identity.api.lifecycle import ToggleRequest
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Company, CompanyBankAccount, CompanyCurrencyAllowance, CompanyFeature
from identity.schemas.banks import BankItem, BankReveal, BankWrite
from identity.schemas.base import Page
from identity.schemas.login import ReasonRequest
from identity.services.audit import record
from identity.services.banks import decrypt_details, encrypt_details

router = APIRouter(prefix="/v1", route_class=StrictRoute, responses=ERROR_RESPONSES)


async def bank_row(
    db: AsyncSession, company_id: uuid.UUID, bank_id: uuid.UUID
) -> CompanyBankAccount:
    row = await db.get(CompanyBankAccount, bank_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("bank account not found")
    return row


async def write_bank(
    db: AsyncSession, request: Request, current: Actor, row: CompanyBankAccount, body: BankWrite
) -> None:
    if await db.get(Currency, body.currency_code) is None:
        raise ValidationFailedError("unknown currency")
    await require_bank_currency(db, row.company_id, body.currency_code)
    for key, value in body.model_dump(exclude={"account_number", "iban"}).items():
        setattr(row, key, value)
    encrypt_details(
        row,
        request.app.state.settings,
        body.account_number.get_secret_value() if body.account_number else None,
        body.iban.get_secret_value() if body.iban else None,
    )
    if row.is_primary:
        previous = await db.scalars(
            select(CompanyBankAccount).where(
                CompanyBankAccount.company_id == row.company_id,
                CompanyBankAccount.currency_code == row.currency_code,
                CompanyBankAccount.is_active.is_(True),
                CompanyBankAccount.is_primary.is_(True),
                CompanyBankAccount.id != row.id,
            )
        )
        for old in previous:
            old.is_primary, old.updated_by = False, current.user_id
            record(
                db,
                current,
                action="company.bank_updated",
                entity="company_bank_account",
                entity_id=old.id,
                company_id=row.company_id,
                changes={"is_primary": {"to": False}},
            )
    row.updated_by = current.user_id


async def require_bank_currency(
    db: AsyncSession, company_id: uuid.UUID, currency_code: str
) -> None:
    company = await db.get(Company, company_id)
    if company is None:
        raise NotFoundError("company not found")
    if currency_code == company.base_currency:
        return
    feature = await db.scalar(
        select(CompanyFeature.id).where(
            CompanyFeature.company_id == company_id,
            CompanyFeature.feature_key == "multi_currency",
            CompanyFeature.is_enabled.is_(True),
        )
    )
    allowance = await db.scalar(
        select(CompanyCurrencyAllowance.id).where(
            CompanyCurrencyAllowance.company_id == company_id,
            CompanyCurrencyAllowance.currency_code == currency_code,
            CompanyCurrencyAllowance.is_active.is_(True),
        )
    )
    if feature is None or allowance is None:
        raise ConflictError("foreign bank currency is not enabled for this company")


@router.post("/companies/{company_id}/bank-accounts", response_model=BankItem, status_code=201)
async def create_bank(
    company_id: uuid.UUID,
    body: BankWrite,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyBankAccount:
    await contact_company(db, current, company_id, True)
    row = CompanyBankAccount(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        is_active=True,
        created_by=current.user_id,
    )
    await write_bank(db, request, current, row, body)
    db.add(row)
    record(
        db,
        current,
        action="company.bank_created",
        entity="company_bank_account",
        entity_id=row.id,
        company_id=company_id,
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/bank-accounts", response_model=Page[BankItem])
async def banks(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BankItem]:
    await contact_company(db, current, company_id, False)
    return await paged(
        db,
        request,
        select(CompanyBankAccount).where(CompanyBankAccount.company_id == company_id),
        model=CompanyBankAccount,
        schema=BankItem,
        limit=limit,
        cursor=cursor,
    )


@router.get("/companies/{company_id}/bank-accounts/{bank_id}", response_model=BankItem)
async def get_bank(
    company_id: uuid.UUID,
    bank_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyBankAccount:
    await contact_company(db, current, company_id, False)
    return await bank_row(db, company_id, bank_id)


@router.put("/companies/{company_id}/bank-accounts/{bank_id}", response_model=BankItem)
async def update_bank(
    company_id: uuid.UUID,
    bank_id: uuid.UUID,
    body: BankWrite,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyBankAccount:
    await contact_company(db, current, company_id, True)
    row = await bank_row(db, company_id, bank_id)
    if not row.is_active:
        raise ConflictError("bank account is inactive")
    await write_bank(db, request, current, row, body)
    record(
        db,
        current,
        action="company.bank_updated",
        entity="company_bank_account",
        entity_id=row.id,
        company_id=company_id,
    )
    await db.flush()
    return row


@router.post("/companies/{company_id}/bank-accounts/{bank_id}/reveal", response_model=BankReveal)
async def reveal_bank(
    company_id: uuid.UUID,
    bank_id: uuid.UUID,
    body: ReasonRequest,
    request: Request,
    response: Response,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BankReveal:
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    claims = getattr(request.state, "verified_claims", None)
    if claims is None or claims.auth_time is None or not 0 <= time.time() - claims.auth_time <= 300:
        raise PermissionDeniedError("fresh provider authentication is required for bank details")
    row = await bank_row(db, company_id, bank_id)
    details = decrypt_details(row, request.app.state.settings)
    record(
        db,
        current,
        action="company.bank_revealed",
        entity="company_bank_account",
        entity_id=row.id,
        company_id=company_id,
        reason=body.reason,
    )
    response.headers["Cache-Control"] = "no-store"
    return BankReveal(**details)


@router.post("/companies/{company_id}/bank-accounts/{bank_id}/lifecycle", response_model=BankItem)
async def bank_lifecycle(
    company_id: uuid.UUID,
    bank_id: uuid.UUID,
    body: ToggleRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyBankAccount:
    await contact_company(db, current, company_id, True)
    row = await bank_row(db, company_id, bank_id)
    if row.is_active != body.is_active:
        if body.is_active:
            await require_bank_currency(db, company_id, row.currency_code)
        row.is_active = body.is_active
        row.deactivated_at = None if body.is_active else utcnow()
        row.deactivated_by = None if body.is_active else current.user_id
        row.updated_by = current.user_id
        if not body.is_active:
            row.is_primary = False
        record(
            db,
            current,
            action="company.bank_lifecycle_changed",
            entity="company_bank_account",
            entity_id=row.id,
            company_id=company_id,
            reason=body.reason,
            changes={"is_active": {"to": body.is_active}},
        )
    await db.flush()
    return row


@router.post("/companies/{company_id}/bank-encryption/rotate")
async def rotate_encryption(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> dict[str, int]:
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    claims = getattr(request.state, "verified_claims", None)
    if claims is None or claims.auth_time is None or not 0 <= time.time() - claims.auth_time <= 300:
        raise PermissionDeniedError("fresh interactive authentication is required")
    from identity.tasks.bank_encryption import rotate_batch

    count = await rotate_batch(db, current, request.app.state.settings, company_id, limit=limit)
    return {"rotated": count}
