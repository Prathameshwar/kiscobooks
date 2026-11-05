"""Explicit reconciliation of unused books; existing calendar identities are retained."""

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import CommandResult
from billing_platform.outbox import audit_payload, emit
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.fiscal import monthly_periods
from accounting.events.financial_contract import period_changed
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.fiscal import FinancialSetup, FiscalPeriod, FiscalYear
from accounting.models.ledger import DocumentSequence
from accounting.models.masters import Account
from accounting.schemas.fiscal import FinancialSetupReconcile
from accounting.tasks.access import authorize, readable, writable
from accounting.tasks.commands import audit, values_of
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.fiscal import snapshot


async def assert_unused(db: AsyncSession, row: FinancialSetup) -> None:
    if row.first_posted_at is not None:
        raise ConflictError("posted books cannot be reconciled")
    # Financial facts can depend on setup before a journal posts (openings, prepared
    # commands, bank/credit facts). Keep this conservative and fail closed.
    calendar = {"financial_setup", "fiscal_year", "fiscal_period", "fiscal_transition"}
    models = {spec.model for name, spec in FINANCIAL_BY_NAME.items() if name not in calendar}
    for model in models:
        if await db.scalar(select(model.id).where(model.company_id == row.company_id).limit(1)):
            raise ConflictError("financial records already depend on this setup")
    if await db.scalar(
        select(Account.id)
        .where(Account.company_id == row.company_id, Account.used_at.is_not(None))
        .limit(1)
    ):
        raise ConflictError("financially used accounts prevent reconciliation")
    if await db.scalar(
        select(DocumentSequence.id).where(DocumentSequence.company_id == row.company_id).limit(1)
    ):
        raise ConflictError("document numbering already depends on this calendar")
    if await db.scalar(
        select(FiscalPeriod.id)
        .where(
            FiscalPeriod.company_id == row.company_id,
            FiscalPeriod.status.not_in(["FUTURE", "OPEN"]),
        )
        .limit(1)
    ):
        raise ConflictError("closed fiscal periods cannot be reconciled")


async def reconcile(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    body: FinancialSetupReconcile,
    key: str,
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["financial_setup"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        facts = financial_context(access)
        if body.configuration_hash != facts.configuration_hash:
            raise ConflictError("company configuration changed; review it before reconciling")
        row = await db.scalar(
            select(FinancialSetup).where(FinancialSetup.company_id == access.context.company_id)
        )
        if row is None:
            raise ConflictError("initialize financial setup first")
        if row.row_version != body.expected_version:
            raise ConflictError("financial setup version changed")
        await assert_unused(db, row)
        values = snapshot(access)
        before = values_of(row, spec)
        required = set(values) - {"timezone", "configuration_hash"}
        if not required <= readable(access, spec, before):
            raise PermissionDeniedError("financial settings must be readable before reconciliation")
        changed = writable(access, spec, before, before | values)
        calendar_changed = any(
            getattr(row, field) != values[field]
            for field in (
                "fiscal_year_start_month",
                "fiscal_year_start_day",
            )
        )
        if calendar_changed:
            year_spec, period_spec = (
                FINANCIAL_BY_NAME["fiscal_year"],
                FINANCIAL_BY_NAME["fiscal_period"],
            )
            access.actor.require_scope("period.manage", target=ScopePath(company_id=row.company_id))
            authorize(access, year_spec, "read")
            authorize(access, period_spec, "read")
            if not {"start_date", "end_date"} <= readable(access, year_spec):
                raise PermissionDeniedError("fiscal dates must be readable before reconciliation")
            # Bounded by the supported calendar year range. Preserve ids and old
            # revisions rather than deleting evidence or invalidating references.
            years = list(
                await db.scalars(
                    select(FiscalYear)
                    .where(FiscalYear.company_id == row.company_id)
                    .order_by(FiscalYear.start_date)
                    .limit(8100)
                )
            )
            for year in years:
                spans = monthly_periods(
                    year.start_date.year, facts.fiscal_year_start_month, facts.fiscal_year_start_day
                )
                periods = list(
                    await db.scalars(
                        select(FiscalPeriod)
                        .where(
                            FiscalPeriod.company_id == row.company_id,
                            FiscalPeriod.fiscal_year_id == year.id,
                        )
                        .order_by(FiscalPeriod.sequence)
                        .limit(13)
                    )
                )
                if len(periods) != 12 or [p.sequence for p in periods] != list(range(1, 13)):
                    raise ConflictError("repair the incomplete fiscal calendar before reconciling")
                required_period = {"sequence", "start_date", "end_date", "status"}
                if any(
                    not required_period
                    <= readable(access, period_spec, values_of(period, period_spec))
                    for period in periods
                ):
                    raise PermissionDeniedError(
                        "fiscal periods must be readable before reconciliation"
                    )
                year_values = {
                    "code": f"FY{spans[0].start_date.year}-{spans[-1].end_date.year}",
                    "start_date": spans[0].start_date,
                    "end_date": spans[-1].end_date,
                }
                year_changed = writable(
                    access,
                    year_spec,
                    values_of(year, year_spec),
                    values_of(year, year_spec) | year_values,
                )
                for name, value in year_values.items():
                    setattr(year, name, value)
                year.row_version += 1
                year.updated_by = access.actor.user_id
                await db.flush()
                audit(db, access, year_spec, year, "update", year_changed)
                for period, span in zip(periods, spans, strict=True):
                    period_values = {
                        "code": f"{year.code}/P{span.sequence:02}",
                        "start_date": span.start_date,
                        "end_date": span.end_date,
                    }
                    period_changed_fields = writable(
                        access,
                        period_spec,
                        values_of(period, period_spec),
                        values_of(period, period_spec) | period_values,
                    )
                    for name, value in period_values.items():
                        setattr(period, name, value)
                    period.row_version += 1
                    period.updated_by = access.actor.user_id
                    await db.flush()
                    audit(db, access, period_spec, period, "update", period_changed_fields)
                    period_changed(db, period)
        for name, value in values.items():
            setattr(row, name, value)
        row.row_version += 1
        row.updated_by = access.actor.user_id
        await db.flush()
        audit(db, access, spec, row, "update", changed)
        emit(
            db,
            aggregate_type="accounting.financial_setup",
            aggregate_id=row.id,
            event_type="accounting.financial_setup.reconciled",
            tenant_id=access.actor.tenant_id,
            payload=audit_payload(
                action="accounting.financial_setup.reconciled",
                category="money",
                entity_type="accounting.financial_setup",
                entity_id=row.id,
                actor_user_id=access.actor.user_id,
                company_id=row.company_id,
                reason=body.reason,
            ),
        )
        return FinancialEffect(row, "period.manage" if calendar_changed else None)

    return await financial_command(
        factory,
        access,
        spec,
        "reconcile",
        body,
        key,
        mutate,
        permission="accounting.finance.manage",
    )
