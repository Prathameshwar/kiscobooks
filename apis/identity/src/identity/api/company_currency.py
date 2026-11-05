"""Versioned company transaction-currency allowance."""

import uuid

from billing_platform.db.reference_models import Currency
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.children import contact_company
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Company, CompanyCurrencyAllowance, CompanyFeature
from identity.schemas.company_currency import (
    CompanyCurrenciesView,
    CurrencyAllowanceView,
    CurrencyAllowanceWrite,
)
from identity.services.audit import record
from identity.services.reference_availability import lock_configuration, require_delivered

router = APIRouter(prefix="/v1", route_class=StrictRoute, responses=ERROR_RESPONSES)


@router.get("/companies/{company_id}/transaction-currencies", response_model=CompanyCurrenciesView)
async def list_currencies(
    company_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyCurrenciesView:
    await contact_company(db, current, company_id, False)
    company = await db.get(Company, company_id)
    assert company is not None
    rows = list(
        await db.scalars(
            select(CompanyCurrencyAllowance)
            .where(CompanyCurrencyAllowance.company_id == company_id)
            .order_by(CompanyCurrencyAllowance.currency_code)
            .limit(65)
        )
    )
    if len(rows) > 64:
        raise ConflictError("company currency allowance limit exceeded")
    return CompanyCurrenciesView(
        base_currency=company.base_currency,
        allowances=[
            CurrencyAllowanceView.model_validate(
                {
                    "id": row.id,
                    "currency_code": row.currency_code,
                    "is_active": row.is_active,
                    "row_version": row.row_version,
                }
            )
            for row in rows
        ],
    )


@router.put(
    "/companies/{company_id}/transaction-currencies/{currency_code}",
    response_model=CurrencyAllowanceView,
)
async def set_currency(
    company_id: uuid.UUID,
    currency_code: str,
    body: CurrencyAllowanceWrite,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CurrencyAllowanceView:
    await contact_company(db, current, company_id, True)
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    assert company is not None
    await lock_configuration(db)
    currency = await db.scalar(
        select(Currency).where(Currency.code == currency_code).with_for_update()
    )
    if currency is None or not currency.is_active or currency_code == company.base_currency:
        raise ValidationFailedError("select an active foreign ISO currency")
    if body.is_active:
        await require_delivered(db, "currency", currency_code)
    feature = await db.scalar(
        select(CompanyFeature).where(
            CompanyFeature.company_id == company_id,
            CompanyFeature.feature_key == "multi_currency",
        )
    )
    if body.is_active and (feature is None or not feature.is_enabled):
        raise ConflictError("enable multi_currency before allowing a foreign currency")
    row = await db.scalar(
        select(CompanyCurrencyAllowance)
        .where(
            CompanyCurrencyAllowance.company_id == company_id,
            CompanyCurrencyAllowance.currency_code == currency_code,
        )
        .with_for_update()
    )
    if row is None:
        if body.expected_version is not None:
            raise ConflictError("currency allowance does not yet exist")
        count = await db.scalars(
            select(CompanyCurrencyAllowance.id)
            .where(CompanyCurrencyAllowance.company_id == company_id)
            .limit(64)
        )
        if len(list(count)) >= 64:
            raise ConflictError("company currency allowance limit exceeded")
        row = CompanyCurrencyAllowance(
            id=uuid7(),
            tenant_id=current.tenant_id,
            company_id=company_id,
            currency_code=currency_code,
            is_active=body.is_active,
            created_by=current.user_id,
            updated_by=current.user_id,
        )
        db.add(row)
    else:
        if body.expected_version != row.row_version:
            raise ConflictError("currency allowance version changed")
        if row.is_active != body.is_active:
            row.is_active = body.is_active
            row.row_version += 1
            row.updated_by = current.user_id
    record(
        db,
        current,
        action="company.currency_allowance_updated",
        entity="company_currency_allowance",
        entity_id=row.id,
        company_id=company_id,
        category="admin",
        changes={"currency_code": {"to": currency_code}, "is_active": {"to": row.is_active}},
    )
    await db.flush()
    return CurrencyAllowanceView.model_validate(
        {
            "id": row.id,
            "currency_code": row.currency_code,
            "is_active": row.is_active,
            "row_version": row.row_version,
        }
    )
