"""As-of open-item balances and aging aggregate dated settlement histories in native SQL."""

import datetime as dt
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import Numeric, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from reports.domain.reconcile import fixed, money
from reports.domain.statements import calculation_evidence
from reports.models.daily_balances import ReportDailyBalance
from reports.models.source_versions import ReportFactVersion
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery
from reports.schemas.requests import RunRequest

CODES = frozenset({"OUTSTANDING_BILLS", "ADVANCES", "AGING"})
BUCKETS = ("CURRENT", "DAYS_1_30", "DAYS_31_60", "DAYS_61_90", "DAYS_OVER_90", "UNKNOWN")


def positions(context: NativeContext, query: RunRequest) -> Any:
    assert query.date_to
    day = query.date_to.isoformat()
    p = ReportFactVersion
    sums = []
    for side, relation in (("debt", "relation_id"), ("credit", "origin_id")):
        allocation = aliased(ReportFactVersion)
        identity = getattr(allocation, relation)
        reversal = allocation.data["reversal_date"].as_string()
        sums.append(
            select(
                identity.label("item_id"),
                cast(func.sum(allocation.amount), Numeric(38, 4)).label("allocated"),
                cast(
                    func.sum(
                        cast(allocation.data[side + "_base_amount"].as_string(), Numeric(38, 4))
                    ),
                    Numeric(38, 4),
                ).label("base_allocated"),
            )
            .where(
                context.view.predicate(allocation),
                allocation.entity == "allocation",
                allocation.posting_date <= query.date_to,
                or_(reversal.is_(None), reversal > day),
            )
            .group_by(identity)
            .subquery()
        )
    debt, credit = sums
    allocated = func.coalesce(debt.c.allocated, 0) + func.coalesce(credit.c.allocated, 0)
    base_allocated = func.coalesce(debt.c.base_allocated, 0) + func.coalesce(
        credit.c.base_allocated, 0
    )
    remaining = cast(p.amount - allocated, Numeric(38, 4))
    base = cast(p.base_amount - base_allocated, Numeric(38, 4))
    reversal = p.data["reversal_date"].as_string()
    statement = (
        context.view.rows("open_item")
        .with_only_columns(
            p.source_id.label("item_id"),
            p.account_id,
            p.party_id,
            p.currency,
            p.base_currency,
            p.wire_bytes,
            p.data["role"].as_string().label("role"),
            p.data["direction"].as_string().label("direction"),
            func.nullif(p.data["due_date"].as_string(), "null").label("due_date"),
            cast(allocated, Numeric(38, 4)).label("allocated"),
            remaining.label("remaining"),
            base.label("base_remaining"),
            (base if query.basis == "BASE" else remaining).label("value"),
        )
        .outerjoin(debt, debt.c.item_id == p.source_id)
        .outerjoin(credit, credit.c.item_id == p.source_id)
        .where(
            p.posting_date <= query.date_to,
            or_(reversal.is_(None), reversal > day),
        )
    )
    if query.account_id or query.group_id or query.party_id or query.role:
        statement = statement.where(p.account_id.in_(context.accounts(query)))
    if query.basis == "TRANSACTION":
        statement = statement.where(p.currency == query.currency)
    return statement


async def controls(
    db: AsyncSession, context: NativeContext, query: RunRequest, source: Any
) -> None:
    c = source.selected_columns
    invalid = (
        source.with_only_columns(c.item_id)
        .where(
            or_(
                c.remaining < 0, c.base_remaining < 0, and_(c.remaining == 0, c.base_remaining != 0)
            )
        )
        .limit(1)
    )
    if await db.scalar(invalid) is not None:
        raise ConflictError("bill allocations exceed owner carrying balances")
    positive = or_(
        and_(c.role == "CUSTOMER", c.direction == "DEBT"),
        and_(c.role != "CUSTOMER", c.direction != "DEBT"),
    )
    values = dict(
        (
            await db.execute(
                source.with_only_columns(
                    c.account_id,
                    cast(func.sum(case((positive, c.value), else_=-c.value)), Numeric(38, 4)),
                ).group_by(c.account_id)
            )
        )
        .tuples()
        .all()
    )
    ledger = LedgerQuery(context, query.model_copy(update={"code": "ACCOUNT_LEDGER"}))
    daily = ReportDailyBalance
    amount = daily.base_amount if query.basis == "BASE" else daily.amount
    selected = [
        key for key in ledger.accounts if context.data.accounts[str(key)]["kind"] == "PARTY"
    ]
    statement = (
        ledger.source_for(
            daily,
            daily.account_id,
            cast(func.sum(case((daily.side == "DEBIT", amount), else_=-amount)), Numeric(38, 4)),
        )
        .where(
            daily.posting_date <= query.date_to,
            daily.account_id.in_(selected),
        )
        .group_by(daily.account_id)
    )
    book = dict((await db.execute(statement)).tuples().all())
    if any(
        values.get(key, Decimal(0)) != book.get(key, Decimal(0))
        for key in values.keys() | book.keys()
    ):
        raise ConflictError("party open items do not reconcile to the as-of general ledger")


def bucket_conditions(c: Any, date_to: dt.date) -> list[Any]:
    """One due-date predicate per ``BUCKETS`` name, as of ``date_to``."""
    conditions = [c.due_date >= date_to.isoformat()]
    for earlier, later in ((0, 30), (30, 60), (60, 90)):
        conditions.append(
            and_(
                c.due_date < (date_to - dt.timedelta(days=earlier)).isoformat(),
                c.due_date >= (date_to - dt.timedelta(days=later)).isoformat(),
            )
        )
    conditions.append(c.due_date < (date_to - dt.timedelta(days=90)).isoformat())
    conditions.append(c.due_date.is_(None))
    return conditions


async def aged(
    db: AsyncSession, source: Any, query: RunRequest, maximum: int
) -> list[dict[str, Any]]:
    assert query.date_to
    c = source.selected_columns
    conditions = bucket_conditions(c, query.date_to)
    # Empty/fully-settled bills cannot create an aging group.
    measures = [("debt", c.direction == "DEBT"), ("unapplied_credit", c.direction == "CREDIT")]
    measures.extend(
        (name, and_(c.direction == "DEBT", condition))
        for name, condition in zip(BUCKETS, conditions, strict=True)
    )
    keys = (c.party_id, c.role, c.account_id)
    rows = (
        (
            await db.execute(
                source.with_only_columns(
                    *keys,
                    *[
                        cast(func.sum(case((condition, c.value), else_=0)), Numeric(38, 4)).label(
                            name
                        )
                        for name, condition in measures
                    ],
                )
                .where(c.remaining != 0)
                .group_by(*keys)
                .order_by(*keys)
                .limit(maximum + 1)
            )
        )
        .mappings()
        .all()
    )
    if len(rows) > maximum:
        raise ConflictError("native aging result exceeds its configured row bound")
    return [
        {
            "row_kind": "AGING",
            "party_id": str(row["party_id"]),
            "role": row["role"],
            "account_id": str(row["account_id"]),
            "currency": query.currency,
            **{name: fixed(money(row[name])) for name, _ in measures},
        }
        for row in rows
    ]


async def execute(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if query.code not in CODES:
        raise ValueError("unsupported native open-item definition")
    await context.validate(db, query)
    source = positions(context, query)
    await controls(db, context, query, source)
    if query.code == "AGING":
        rows = await aged(db, source, query, maximum)
        for row in rows:
            row["currency"] = query.currency or context.data.currency
            account = context.data.accounts[row["account_id"]]
            row.update(account_code=account["code"], account_name=account["name"])
    else:
        rows = []
        after = None
        size = 0
        while True:
            c = source.selected_columns
            statement = source.where(c.remaining != 0)
            if query.code == "ADVANCES":
                statement = statement.where(c.direction == "CREDIT")
            if after is not None:
                statement = statement.where(c.item_id > after)
            values = (await db.execute(statement.order_by(c.item_id).limit(200))).mappings().all()
            if not values:
                break
            if len(rows) + len(values) > maximum:
                raise ConflictError("native bill result exceeds its configured row bound")
            items = await context.view.lookup(
                db, "open_item", [value["item_id"] for value in values]
            )
            assert query.date_to
            for value in values:
                item = items[value["item_id"]].data
                assert item is not None
                days = (
                    max(0, (query.date_to - dt.date.fromisoformat(item["due_date"])).days)
                    if item["due_date"]
                    else None
                )
                bucket = BUCKETS[
                    5
                    if days is None
                    else 0
                    if days == 0
                    else 1
                    if days <= 30
                    else 2
                    if days <= 60
                    else 3
                    if days <= 90
                    else 4
                ]
                row = {
                    "row_kind": "BILL",
                    "item_id": str(value["item_id"]),
                    **{
                        key: item[key]
                        for key in (
                            "account_id",
                            "party_id",
                            "role",
                            "direction",
                            "reference",
                            "document_date",
                            "posting_date",
                            "due_date",
                            "currency",
                            "base_currency",
                        )
                    },
                    "original_amount": item["amount"],
                    "account_code": context.data.accounts[item["account_id"]]["code"],
                    "account_name": context.data.accounts[item["account_id"]]["name"],
                    "allocated_amount": fixed(money(value["allocated"])),
                    "remaining": fixed(money(value["remaining"])),
                    "base_remaining": fixed(money(value["base_remaining"])),
                    "report_amount": fixed(money(value["value"])),
                    "report_currency": query.currency or context.data.currency,
                    "tracking": item["terms"].get(
                        "tracking", "NEW_REF" if item["direction"] == "DEBT" else "ON_ACCOUNT"
                    ),
                    "days_overdue": days,
                    "aging_bucket": bucket,
                }
                size += len(canonical_json(row))
                if size > 32 * 1024 * 1024:
                    raise ConflictError("native bill result exceeds its materialization byte bound")
                rows.append(row)
            after = values[-1]["item_id"]
    for row in rows:
        row["period"] = "CURRENT"
    return rows, calculation_evidence(context.data, query, context.coverage, rows)
