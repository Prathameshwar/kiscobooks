"""Versioned, effective-dated overdue charge policies."""

import datetime as dt
import uuid

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.charges import ChargeAssessment, ChargePolicy
from accounting.models.masters import Account
from accounting.schemas.charges import ChargePolicyClose, ChargePolicyCreate
from accounting.tasks.finance_records import change_row, create_row
from accounting.tasks.financial_commands import FinancialEffect, financial_command
from accounting.tasks.party_documents import party_account


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: ChargePolicyCreate, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        account = await party_account(db, access, body.account_id)
        offset = await company_object(
            db, Account, body.offset_account_id, company_id=account.company_id
        )
        if offset.kind != "GENERAL" or offset.status != "ACTIVE" or offset.currency_mode != "BASE":
            raise ValidationFailedError(
                "charge counterpart requires an active base-currency general account"
            )
        expected = (
            access.context.base_currency
            if account.currency_mode == "BASE"
            else account.currency
            if account.currency_mode == "FIXED"
            else body.currency
        )
        if body.currency != expected:
            raise ValidationFailedError("charge policy currency differs from its account")
        if body.valid_to is not None and body.valid_to < body.valid_from:
            raise ValidationFailedError("charge policy end precedes its start")
        if body.cap is not None and body.cap < body.minimum:
            raise ValidationFailedError("charge cap cannot be less than its minimum")
        if body.method == "FIXED" and body.compound != "SIMPLE":
            raise ValidationFailedError("fixed charges cannot compound")
        overlap = await db.scalar(
            select(ChargePolicy.id)
            .where(
                ChargePolicy.company_id == account.company_id,
                ChargePolicy.account_id == account.id,
                ChargePolicy.currency == body.currency,
                (ChargePolicy.valid_to.is_(None)) | (ChargePolicy.valid_to >= body.valid_from),
                *([ChargePolicy.valid_from <= body.valid_to] if body.valid_to else []),
            )
            .limit(1)
        )
        if overlap:
            raise ConflictError("charge policy dates overlap an existing policy")
        return FinancialEffect(await create_row(db, access, "charge_policy", **body.model_dump()))

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["charge_policy"],
        "create",
        body,
        key,
        mutate,
        permission="accounting.charges.manage",
        status=201,
    )


async def close(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ChargePolicyClose,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, ChargePolicy, object_id, company_id=access.context.company_id
        )
        if row.row_version != body.expected_version:
            raise ConflictError("charge policy version changed")
        if body.valid_to < row.valid_from or (
            row.valid_to is not None and body.valid_to > row.valid_to
        ):
            raise ValidationFailedError("closing can only shorten a policy's effective dates")
        later = await db.scalar(
            select(ChargeAssessment.id)
            .where(
                ChargeAssessment.company_id == row.company_id,
                ChargeAssessment.policy_id == row.id,
                ChargeAssessment.status.not_in(["REVERSED", "REJECTED"]),
                ChargeAssessment.coverage_end_date
                > (
                    body.valid_to + dt.timedelta(days=1)
                    if body.valid_to < dt.date.max
                    else dt.date.max
                ),
            )
            .limit(1)
        )
        if later:
            raise ConflictError("policy cannot end before its existing assessment coverage")
        await change_row(db, access, "charge_policy", row, "close", valid_to=body.valid_to)
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["charge_policy"],
        "close",
        body,
        key,
        mutate,
        permission="accounting.charges.manage",
        object_id=object_id,
    )
