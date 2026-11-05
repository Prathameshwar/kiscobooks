"""Native grouped inputs reuse the reference financial rules without retaining GL lines."""

import datetime as dt
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import Numeric, case, cast, extract, func
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.statements import STATEMENTS, Facts, calculate_data
from reports.models.daily_balances import ReportDailyBalance
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery
from reports.schemas.requests import RunRequest

CODES = STATEMENTS | {"ACCOUNT_SUMMARY"}


class AggregatedFacts(Facts):
    def __init__(self, dimensions: Facts, lines: list[dict[str, Any]]):
        self.rows = dimensions.rows
        self.accounts, self.groups, self.journals = (
            dimensions.accounts,
            dimensions.groups,
            dimensions.journals,
        )
        self.finance, self.currency = dimensions.finance, dimensions.currency
        self.aggregated = lines

    def lines(self, query: RunRequest) -> list[dict[str, Any]]:
        return self.aggregated


def grouping(context: NativeContext, query: RunRequest) -> tuple[Any, Any]:
    p = ReportDailyBalance
    start, end = query.date_from, query.date_to
    assert start is not None and end is not None
    if query.code == "ACCOUNT_SUMMARY" and query.grain == "MONTH":
        bucket = case(
            (p.posting_date < start, 0),
            ((p.opening_effect.is_(True)) & (p.posting_date == start), -1),
            else_=extract("year", p.posting_date) * 100 + extract("month", p.posting_date),
        )

        def date_for(value: Any, opening: bool) -> dt.date:
            if value == 0:
                return start - dt.timedelta(days=1)
            if value == -1:
                return start
            first = dt.date(int(value) // 100, int(value) % 100, 1)
            boundary = start + dt.timedelta(days=1) if opening and start < dt.date.max else start
            return max(first, boundary)

        return bucket, date_for
    if query.code == "ACCOUNT_SUMMARY":
        prior = start - dt.timedelta(days=1) if start > dt.date.min else dt.date.min
        bucket = case((p.posting_date < start, prior), else_=p.posting_date)
    else:
        boundaries = {start}
        if start < end:
            boundaries.add(start + dt.timedelta(days=1))
        if query.code == "BALANCE_SHEET":
            for year in context.data.rows["fiscal_year"].values():
                if year["start_date"] <= end.isoformat() <= year["end_date"]:
                    boundaries.add(dt.date.fromisoformat(year["start_date"]))
        previous, conditions = context.coverage, []
        for boundary in sorted(boundaries):
            conditions.append((p.posting_date < boundary, previous))
            previous = boundary
        bucket = case(*conditions, else_=previous)
    # MySQL CASE expressions over bound date literals return strings; SQLite's
    # Date result processor returns dates. Normalize at this database boundary.
    return bucket, lambda value, opening: (
        dt.date.fromisoformat(value) if isinstance(value, str) else value
    )


async def reduced(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> AggregatedFacts:
    await context.validate(db, query)
    p = ReportDailyBalance
    # The ledger source helper supplies the same frozen scope, account and currency selection.
    source = LedgerQuery(context, query.model_copy(update={"code": "ACCOUNT_LEDGER"}))
    bucket, date_for = grouping(context, query)
    amount = p.base_amount if query.basis == "BASE" else p.amount
    statement = (
        source.source_for(
            p,
            p.account_id,
            p.side,
            p.opening_effect,
            bucket.label("bucket"),
            cast(func.sum(amount), Numeric(38, 4)),
        )
        .where(
            p.posting_date <= query.date_to,
        )
        .group_by(p.account_id, p.side, p.opening_effect, bucket)
        .limit(maximum + 1)
    )
    groups = (await db.execute(statement)).all()
    if len(groups) > maximum:
        raise ConflictError("native financial aggregate exceeds its configured result bound")
    lines = []
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for account, side, opening, period, amount in groups:
            if not isinstance(amount, Decimal):
                raise ConflictError("native financial aggregate must return an exact Decimal")
            lines.append(
                {
                    "account_id": str(account),
                    "side": side,
                    "opening_effect": opening,
                    "posting_date": date_for(period, opening),
                    "value": amount,
                    "signed": amount if side == "DEBIT" else -amount,
                }
            )
    return AggregatedFacts(context.data, lines)


async def execute(
    db: AsyncSession,
    context: NativeContext,
    query: RunRequest,
    maximum: int,
    *,
    opening_boundary: dt.date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if query.code not in CODES:
        raise ValueError("unsupported native financial definition")
    current = query.model_copy(update={"comparative_from": None, "comparative_to": None})
    data = await reduced(db, context, current, maximum)
    rows, evidence = calculate_data(
        data, current, context.coverage, maximum=maximum, opening_boundary=opening_boundary
    )
    if query.comparative_from and query.comparative_to:
        comparison = current.model_copy(
            update={"date_from": query.comparative_from, "date_to": query.comparative_to}
        )
        data = await reduced(db, context, comparison, maximum)
        other, _ = calculate_data(data, comparison, context.coverage, maximum=maximum - len(rows))
        rows.extend(row | {"period": "COMPARATIVE"} for row in other)
    if len(rows) > maximum:
        raise ConflictError("native financial result exceeds its configured row bound")
    return rows, evidence | {"row_count": len(rows)}
