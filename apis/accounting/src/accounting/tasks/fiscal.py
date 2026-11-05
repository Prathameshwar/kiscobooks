"""Fiscal commands serialize with every journal write on the Accounting company lock."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandResult
from billing_platform.ids import uuid7
from billing_platform.posting import PostingPeriod, assert_postable
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.fiscal import monthly_periods, transition_permission
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.fiscal import FinancialSetup, FiscalPeriod, FiscalTransition, FiscalYear
from accounting.models.ledger import Journal
from accounting.schemas.fiscal import FiscalYearGenerate, PeriodTransition
from accounting.schemas.masters import Input
from accounting.tasks.access import writable
from accounting.tasks.commands import audit, values_of
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)


def snapshot(access: Access) -> dict[str, Any]:
    facts = financial_context(access)
    return {
        key: getattr(facts, key)
        for key in (
            "books_begin_date",
            "fiscal_year_start_month",
            "fiscal_year_start_day",
            "amount_precision",
            "rounding_mode",
            "timezone",
            "configuration_hash",
        )
    } | {"base_currency": access.context.base_currency}


async def setup(db: AsyncSession, access: Access) -> FinancialSetup:
    row = await db.scalar(
        select(FinancialSetup).where(FinancialSetup.company_id == access.context.company_id)
    )
    if row is None:
        raise ConflictError("initialize financial setup first")
    financial_context(access)
    if not frozen_settings_match(row, access):
        raise ConflictError("authoritative company settings differ from financial setup")
    return row


def frozen_settings_match(row: FinancialSetup, access: Access) -> bool:
    """Only the company's immutable book settings define fiscal continuity.

    The configuration digest and timezone may legitimately change after setup.
    The latter is read from the current signed context by the posting guard.
    """
    facts = access.context.finance
    if facts is None:
        return False
    return (
        row.books_begin_date == facts.books_begin_date
        and row.fiscal_year_start_month == facts.fiscal_year_start_month
        and row.fiscal_year_start_day == facts.fiscal_year_start_day
        and row.amount_precision == facts.amount_precision
        and row.rounding_mode == facts.rounding_mode
        and row.base_currency == access.context.base_currency
    )


async def initialize(
    factory: async_sessionmaker[AsyncSession], access: Access, key: str
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["financial_setup"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        from accounting.tasks.default_accounts import provision
        from accounting.tasks.stock_policy import provision_standard

        existing = await db.scalar(
            select(FinancialSetup).where(FinancialSetup.company_id == access.context.company_id)
        )
        if existing is not None:
            row = await setup(db, access)
            # A company whose books were set up before inventory was on catches up here.
            await provision_standard(db, access, row.books_begin_date)
            await provision(db, access, row.books_begin_date)
            return FinancialEffect(row)
        values = snapshot(access)
        changed = writable(access, spec, {}, values)
        row = FinancialSetup(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=access.context.company_id,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
            **values,
        )
        db.add(row)
        await db.flush()
        audit(db, access, spec, row, "create", changed)
        # A company with inventory starts with its standard stock accounts mapped from day one.
        await provision_standard(db, access, row.books_begin_date)
        await provision(db, access, row.books_begin_date)
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        spec,
        "initialize",
        Input(),
        key,
        mutate,
        # Either key. `accounting.finance.initialize` is the narrow one an administrator
        # holds, so a newly created company can be set up without also granting the
        # opening-balance controls that `accounting.finance.manage` carries
        # (docs/roles-permissions.md decision log 2026-10-21); the broader key keeps
        # working for the controller grants that already had it.
        permission=("accounting.finance.initialize", "accounting.finance.manage"),
        # Initial stock and tax ledgers need the same bounded budget as the chart.
        timeout_seconds=30,
    )


async def generate(
    factory: async_sessionmaker[AsyncSession], access: Access, body: FiscalYearGenerate, key: str
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["fiscal_year"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        config = await setup(db, access)
        spans = monthly_periods(
            body.start_year, config.fiscal_year_start_month, config.fiscal_year_start_day
        )
        existing = await db.scalar(
            select(FiscalYear).where(
                FiscalYear.company_id == access.context.company_id,
                FiscalYear.start_date == spans[0].start_date,
            )
        )
        if existing is not None:
            return FinancialEffect(existing)
        overlap = await db.scalar(
            select(FiscalYear.id)
            .where(
                FiscalYear.company_id == access.context.company_id,
                FiscalYear.start_date <= spans[-1].end_date,
                FiscalYear.end_date >= spans[0].start_date,
            )
            .limit(1)
        )
        if overlap is not None:
            raise ConflictError("fiscal year overlaps an existing year")
        values = {
            "code": f"FY{body.start_year}-{spans[-1].end_date.year}",
            "start_date": spans[0].start_date,
            "end_date": spans[-1].end_date,
        }
        changed = writable(access, spec, {}, values | body.model_dump())
        row = FiscalYear(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=access.context.company_id,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
            **values,
        )
        db.add(row)
        await db.flush()
        audit(db, access, spec, row, "create", changed)
        period_spec = FINANCIAL_BY_NAME["fiscal_period"]
        for span in spans:
            period_values = {
                "fiscal_year_id": row.id,
                "sequence": span.sequence,
                "code": f"{row.code}/P{span.sequence:02}",
                "start_date": span.start_date,
                "end_date": span.end_date,
                "status": "FUTURE",
            }
            changed = writable(access, period_spec, {}, period_values)
            period = FiscalPeriod(
                id=uuid7(),
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                created_by=access.actor.user_id,
                updated_by=access.actor.user_id,
                **period_values,
            )
            db.add(period)
            await db.flush()
            audit(db, access, period_spec, period, "create", changed)
            from accounting.events.financial_contract import period_changed

            period_changed(db, period)
        return FinancialEffect(row)

    return await financial_command(
        factory, access, spec, "generate", body, key, mutate, permission="period.manage"
    )


async def transition(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: PeriodTransition,
    key: str,
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["fiscal_period"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        await setup(db, access)
        row = await company_object(
            db, FiscalPeriod, object_id, company_id=access.context.company_id
        )
        if row.row_version != body.expected_version:
            raise ConflictError("fiscal period version changed")
        preceding = tuple(
            await db.scalars(
                select(FiscalPeriod.status).where(
                    FiscalPeriod.company_id == row.company_id,
                    FiscalPeriod.fiscal_year_id == row.fiscal_year_id,
                    FiscalPeriod.sequence < row.sequence,
                )
            )
        )
        required = transition_permission(row.status, body.status, preceding)
        access.actor.require_scope(required, target=ScopePath(company_id=row.company_id))
        if body.status in {"SOFT_CLOSED", "CLOSED", "LOCKED"}:
            pending = await db.scalar(
                select(Journal.id)
                .where(
                    Journal.company_id == row.company_id,
                    Journal.posting_date >= row.start_date,
                    Journal.posting_date <= row.end_date,
                    Journal.status.in_(["DRAFT", "PREPARED"]),
                )
                .limit(1)
            )
            if pending is not None:
                raise ConflictError("period has draft or prepared journals")
            from accounting.models.voucher_money import VoucherMoneyIntent

            execution = await db.scalar(
                select(VoucherMoneyIntent.id)
                .where(
                    VoucherMoneyIntent.company_id == row.company_id,
                    VoucherMoneyIntent.posting_date.between(row.start_date, row.end_date),
                    VoucherMoneyIntent.status == "PREPARED",
                )
                .limit(1)
            )
            if execution is not None:
                raise ConflictError(
                    "reconcile pending voucher executions before closing the period"
                )
            from accounting.tasks.reconciliation import closing_checks

            await closing_checks(db, access, row)
        before = values_of(row, spec)
        changed = writable(
            access, spec, before, before | {"status": body.status, "reason": body.reason}
        )
        evidence = FiscalTransition(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=row.company_id,
            period_id=row.id,
            from_status=row.status,
            to_status=body.status,
            reason=body.reason,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
        )
        db.add(evidence)
        row.status = body.status
        row.row_version += 1
        row.updated_by = access.actor.user_id
        await db.flush()
        audit(db, access, spec, row, "transition", changed)
        from accounting.events.financial_contract import period_changed

        period_changed(db, row)
        return FinancialEffect(row, required)

    # Replays still require the authority corresponding to the requested transition.
    required = {
        "SOFT_CLOSED": "period.close",
        "CLOSED": "period.close",
        "LOCKED": "period.lock",
    }.get(body.status)
    if body.status == "OPEN":
        # Both opening and reopening are checked precisely inside the locked mutation.
        target = ScopePath(company_id=access.context.company_id)
        if not (
            access.actor.allows_scope("period.manage", target=target)
            or access.actor.allows_scope("period.reopen", target=target)
        ):
            access.actor.require_scope("period.manage", target=target)
    return await financial_command(
        factory,
        access,
        spec,
        "transition",
        body,
        key,
        mutate,
        permission=required,
        object_id=object_id,
    )


async def posting_period(db: AsyncSession, access: Access, posting_date: dt.date) -> FiscalPeriod:
    await setup(db, access)
    periods = list(
        await db.scalars(
            select(FiscalPeriod)
            .where(
                FiscalPeriod.company_id == access.context.company_id,
                FiscalPeriod.start_date <= posting_date,
                FiscalPeriod.end_date >= posting_date,
            )
            .limit(2)
        )
    )
    if len(periods) > 1:
        raise ConflictError("posting date resolves to multiple fiscal periods")
    row = periods[0] if periods else None
    resolved = (
        None
        if row is None
        else PostingPeriod(
            row.id, row.tenant_id, row.company_id, row.start_date, row.end_date, row.status
        )
    )
    assert_postable(
        access.context.company_id,
        posting_date,
        access.actor,
        context=access.context,
        period=resolved,
    )
    assert row is not None
    return row
