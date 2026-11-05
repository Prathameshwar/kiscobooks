"""Small SQL aggregates over immutable daily and as-of owner projections."""

import datetime as dt
import uuid
from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import Numeric, and_, case, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reconcile import fixed, money
from reports.models.core import ReportGeneration
from reports.models.daily_balances import ReportDailyBalance
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery
from reports.queries.native_open_items import BUCKETS, bucket_conditions, controls, positions
from reports.schemas.overview import (
    CompanyOverview,
    OverviewBuckets,
    OverviewDay,
    OverviewLedger,
    OverviewOpenItems,
    OverviewParty,
    OverviewPosition,
    OverviewTotals,
)
from reports.schemas.requests import RunRequest

ROLES = ("CUSTOMER", "SUPPLIER")
TOP = 5
OVERDUE = BUCKETS[1:5]


def _sum(value: Any) -> Any:
    return cast(func.coalesce(func.sum(value), 0), Numeric(38, 4))


def _party_name(fact: Any, fallback: str) -> str:
    """The party's own name from the frozen source; a ledger's name only if it has none."""
    name = fact.data.get("name") if fact is not None and fact.data else None
    return name if isinstance(name, str) and name.strip() else fallback


def _ledger_names(context: NativeContext) -> dict[str, str]:
    """One ledger name per party, for a party fact that carries no name."""
    names: dict[str, str] = {}
    for _key, row in sorted(context.data.accounts.items()):
        if row["party_id"] is not None:
            names.setdefault(row["party_id"], row["name"])
    return names


async def _top_parties(
    db: AsyncSession, source: Any, role: str, due: Mapping[str, Any]
) -> list[Any]:
    """Largest net balances of one role, one row per *party* however many ledgers it holds.

    One bounded grouped read, never the bill list. ``party_id`` is the open item's own party,
    so two ledgers of one party (one per currency, say) are summed before they are ranked.
    """
    c = source.selected_columns
    bill, credit = c.direction == "DEBT", c.direction == "CREDIT"
    net = _sum(case((bill, c.base_remaining), (credit, -c.base_remaining), else_=0))
    overdue = _sum(
        case((and_(bill, or_(*(due[name] for name in OVERDUE))), c.base_remaining), else_=0)
    )
    rows = await db.execute(
        source.with_only_columns(c.party_id, net.label("outstanding"), overdue.label("due"))
        .where(c.role == role)
        .group_by(c.party_id)
        .having(net > 0)
        .order_by(net.desc(), c.party_id)
        .limit(TOP)
    )
    return [tuple(row) for row in rows.all()]


async def _open_items(
    db: AsyncSession, context: NativeContext, source: Any, last: dt.date
) -> dict[str, OverviewOpenItems]:
    """Bills by age and unapplied credit per role, as of the period end.

    ``DEBT`` is the bill side for both roles (a customer invoice, a supplier bill) and
    ``CREDIT`` the unapplied side, so a positive net always means money still to move.
    """
    c = source.selected_columns
    bill, credit = c.direction == "DEBT", c.direction == "CREDIT"
    due = dict(zip(BUCKETS, bucket_conditions(c, last), strict=True))
    rows = (
        (
            await db.execute(
                source.with_only_columns(
                    c.role,
                    _sum(case((credit, c.base_remaining), else_=0)).label("advances"),
                    *(
                        _sum(case((and_(bill, due[name]), c.base_remaining), else_=0)).label(name)
                        for name in BUCKETS
                    ),
                )
                .where(c.role.in_(ROLES))
                .group_by(c.role)
                .limit(len(ROLES))
            )
        )
        .mappings()
        .all()
    )
    by_role = {row["role"]: row for row in rows}
    ranked = {role: await _top_parties(db, source, role, due) for role in ROLES}
    # At most TOP ids per role: one bounded lookup names every listed party.
    facts = await context.view.lookup(
        db, "party", {party for parties in ranked.values() for party, *_ in parties}
    )
    ledgers = _ledger_names(context)
    return {
        role: _summary(
            by_role.get(role),
            [
                OverviewParty(
                    party_id=party,
                    name=_party_name(facts.get(party), ledgers.get(str(party), "Unnamed party")),
                    outstanding=fixed(money(outstanding)),
                    overdue=fixed(money(overdue)),
                )
                for party, outstanding, overdue in ranked[role]
            ],
        )
        for role in ROLES
    }


def _summary(row: Mapping[Any, Any] | None, parties: list[OverviewParty]) -> OverviewOpenItems:
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        amount = {
            name: money(row[name]) if row is not None else Decimal(0)
            for name in ("advances", *BUCKETS)
        }
        gross = sum((amount[name] for name in BUCKETS), Decimal(0))
        overdue = sum((amount[name] for name in OVERDUE), Decimal(0))
        return OverviewOpenItems(
            gross=fixed(gross),
            advances=fixed(amount["advances"]),
            net=fixed(gross - amount["advances"]),
            overdue=fixed(overdue),
            buckets=OverviewBuckets(**{name.lower(): fixed(amount[name]) for name in BUCKETS}),
            parties=parties,
        )


async def calculate_overview(
    db: AsyncSession,
    generation: ReportGeneration,
    *,
    fiscal_year_id: uuid.UUID | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
    today: dt.date,
) -> CompanyOverview:
    context = await NativeContext.load(db, generation.company_id, generation.id)
    years = context.data.rows["fiscal_year"]
    selected = (
        str(fiscal_year_id)
        if fiscal_year_id
        else next(
            (
                key
                for key, year in years.items()
                if year["start_date"] <= today.isoformat() <= year["end_date"]
            ),
            None,
        )
    )
    if selected is None or selected not in years:
        raise ConflictError("selected financial year requires a fresh company source")
    year = years[selected]
    start, end = dt.date.fromisoformat(year["start_date"]), dt.date.fromisoformat(year["end_date"])
    first = date_from or max(start, context.coverage)
    last = date_to or min(end, today)
    if first < start or last > end or first > last or (last - first).days > 365:
        raise ValidationFailedError("select a covered range of at most 366 days within this year")
    query = RunRequest(
        generation_id=generation.id, code="ACCOUNT_LEDGER", date_from=first, date_to=last
    )
    await context.validate(db, query)
    ledger = LedgerQuery(context, query)
    daily = ReportDailyBalance
    signed = case((daily.side == "DEBIT", daily.base_amount), else_=-daily.base_amount)
    live = daily.opening_effect.is_(False)
    accounts = context.data.accounts

    def classified(kind: str | None = None, nature: str | None = None) -> list[uuid.UUID]:
        return [
            uuid.UUID(key)
            for key, row in accounts.items()
            if (kind is None or row["kind"] == kind)
            and (nature is None or context.data.nature(row) == nature)
        ]

    def total(keys: list[uuid.UUID], value: Any) -> Any:
        return _sum(case((daily.account_id.in_(keys), value), else_=0))

    cash_keys, bank_keys = classified(kind="CASH"), classified(kind="BANK")
    cash, bank, opening = (
        await db.execute(
            ledger.source_for(
                daily,
                total(cash_keys, signed),
                total(bank_keys, signed),
                total(cash_keys + bank_keys, case((daily.posting_date < first, signed), else_=0)),
            ).where(daily.posting_date <= last)
        )
    ).one()
    # Opening-effect rows move cash and bank (they are balances) but are not activity.
    activity = ledger.source_for(
        daily,
        daily.posting_date,
        total(classified(nature="INCOME"), case((live, -signed), else_=0)).label("income"),
        total(classified(nature="EXPENSE"), case((live, signed), else_=0)).label("expenses"),
        total(cash_keys + bank_keys, signed).label("cash_and_bank"),
    ).where(daily.posting_date >= first, daily.posting_date <= last)
    records = (
        await db.execute(
            activity.group_by(daily.posting_date).order_by(daily.posting_date).limit(367)
        )
    ).all()
    if len(records) > 366:
        raise ConflictError("overview daily series exceeds its supported bound")
    expense = func.sum(signed)
    ranked = (
        await db.execute(
            ledger.source_for(daily, daily.account_id, cast(expense, Numeric(38, 4)))
            .where(
                daily.account_id.in_(classified(nature="EXPENSE")),
                daily.posting_date >= first,
                daily.posting_date <= last,
                live,
            )
            .group_by(daily.account_id)
            .having(expense > 0)
            .order_by(expense.desc(), daily.account_id)
            .limit(TOP)
        )
    ).all()
    source = positions(context, query)
    await controls(db, context, query, source)
    open_items = await _open_items(db, context, source, last)
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        by_day = {
            date: (money(income), money(expenses), money(moved))
            for date, income, expenses, moved in records
        }
        zero = (Decimal(0), Decimal(0), Decimal(0))
        series: list[OverviewDay] = []
        position: list[OverviewPosition] = []
        running = money(opening)
        for index in range((last - first).days + 1):
            day = first + dt.timedelta(days=index)
            income_day, expenses_day, moved = by_day.get(day, zero)
            running += moved
            series.append(
                OverviewDay(date=day, income=fixed(income_day), expenses=fixed(expenses_day))
            )
            position.append(OverviewPosition(date=day, cash_and_bank=fixed(running)))
        income = sum((money(row.income) for row in series), Decimal(0))
        expenses = sum((money(row.expenses) for row in series), Decimal(0))
        top_expenses = [
            OverviewLedger(
                account_id=account_id,
                name=accounts[str(account_id)]["name"],
                amount=fixed(money(amount)),
            )
            for account_id, amount in ranked
        ]
        other = expenses - sum((money(row.amount) for row in top_expenses), Decimal(0))
        totals = OverviewTotals(
            cash=fixed(cash),
            bank=fixed(bank),
            net_receivable=open_items["CUSTOMER"].net,
            net_payable=open_items["SUPPLIER"].net,
            income=fixed(income),
            expenses=fixed(expenses),
            net_income=fixed(income - expenses),
        )
    return CompanyOverview(
        company_id=generation.company_id,
        generation_id=generation.id,
        snapshot_id=generation.snapshot_id,
        source_created_at=generation.created_at
        if generation.created_at.tzinfo
        else generation.created_at.replace(tzinfo=dt.UTC),
        fiscal_year_id=uuid.UUID(selected),
        year_start=start,
        coverage_start=context.coverage,
        date_from=first,
        date_to=last,
        currency=context.data.currency,
        earlier_history_unavailable=context.coverage > start,
        totals=totals,
        series=series,
        position=position,
        receivables=open_items["CUSTOMER"],
        payables=open_items["SUPPLIER"],
        top_expenses=top_expenses,
        other_expenses=fixed(other),
    )
