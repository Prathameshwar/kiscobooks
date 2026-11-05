"""Year-boundary review over retained books; no annual postings or balance replacement."""

import calendar
import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from billing_platform.errors import ConflictError

from reports.domain.reconcile import fixed, money

if TYPE_CHECKING:
    from reports.domain.statements import Facts
    from reports.schemas.requests import RunRequest


def calendars(
    data: "Facts", query: "RunRequest", coverage: dt.date
) -> tuple[dict[str, Any], dict[str, Any]]:
    years = data.rows["fiscal_year"]
    targets = [
        (identity, row)
        for identity, row in years.items()
        if row["start_date"] == str(query.date_from) and row["end_date"] == str(query.date_to)
    ]
    if len(targets) != 1:
        raise ConflictError("select a complete financial year for the continuity review")
    target_id, target = targets[0]
    assert query.date_from is not None
    cutoff = query.date_from - dt.timedelta(days=1)
    previous = [
        (identity, row) for identity, row in years.items() if row["end_date"] == str(cutoff)
    ]
    if len(previous) != 1:
        raise ConflictError(
            "generate a contiguous previous financial year before reviewing continuity"
        )
    books = dt.date.fromisoformat(data.finance[0]["books_begin_date"])
    if coverage != books or cutoff < books:
        raise ConflictError(
            "continuity requires retained coverage of the original books before the next year"
        )
    previous_id, prior = previous[0]
    month, day = (
        data.finance[0]["fiscal_year_start_month"],
        data.finance[0]["fiscal_year_start_day"],
    )
    for year in (prior, target):
        start = dt.date.fromisoformat(year["start_date"])
        try:
            first = dt.date(start.year, month, min(day, calendar.monthrange(start.year, month)[1]))
            following = dt.date(
                start.year + 1, month, min(day, calendar.monthrange(start.year + 1, month)[1])
            )
        except ValueError as error:
            raise ConflictError("the frozen company fiscal calendar is invalid") from error
        if start != first or year["end_date"] != str(following - dt.timedelta(days=1)):
            raise ConflictError(
                "the complete financial year must match the frozen company calendar"
            )
    return prior | {"id": previous_id}, target | {"id": target_id}


def continuity(
    data: "Facts",
    query: "RunRequest",
    coverage: dt.date,
    open_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    from reports.domain.registers import outstanding
    from reports.domain.statements import balance_sheet, balances

    prior, target = calendars(data, query, coverage)
    assert query.date_from is not None
    prior_query = query.model_copy(
        update={
            "date_from": max(coverage, dt.date.fromisoformat(prior["start_date"])),
            "date_to": dt.date.fromisoformat(prior["end_date"]),
        }
    )
    opening_query = query.model_copy(update={"date_to": query.date_from})
    closing = {row["account_id"]: row for row in balances(data, prior_query)}
    opening = balances(data, opening_query)
    rows: list[dict[str, Any]] = []
    for row in opening:
        before, after = money(closing[row["account_id"]]["closing"]), money(row["opening"])
        rows.append(
            {
                "row_kind": "ACCOUNT_CONTINUITY",
                "account_id": row["account_id"],
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "group_id": row["group_id"],
                "nature": row["nature"],
                "currency": data.currency,
                "previous_closing": fixed(before),
                "next_opening": fixed(after),
                "difference": fixed(after - before),
                "reconciled": after == before,
            }
        )
    bills = outstanding(data, prior_query) if open_items is None else open_items
    for bill in sorted(bills, key=lambda row: row["item_id"]):
        amount = bill["base_remaining"]
        rows.append(
            {
                "row_kind": "BILL_CONTINUITY"
                if bill["direction"] == "DEBT"
                else "ADVANCE_CONTINUITY",
                **{
                    key: bill[key]
                    for key in (
                        "account_id",
                        "account_code",
                        "account_name",
                        "item_id",
                        "reference",
                        "party_id",
                        "role",
                        "direction",
                        "due_date",
                    )
                },
                "currency": data.currency,
                "transaction_currency": bill["currency"],
                "previous_closing": amount,
                "next_opening": amount,
                "difference": "0.0000",
                "reconciled": True,
            }
        )
    # Prior P&L rolls into the derived accumulated-earnings bridge, while next-year
    # operating activity stays in current-year earnings. These are not posted transfers.
    before = sum(
        (money(row["amount"]) for row in balance_sheet(data, prior_query) if row.get("derived")),
        Decimal(0),
    )
    after = sum(
        (
            money(row["amount"])
            for row in balance_sheet(data, opening_query)
            if row.get("derived") and row["row_kind"] != "CURRENT_YEAR_EARNINGS"
        ),
        Decimal(0),
    )
    rows.append(
        {
            "row_kind": "EARNINGS_CONTINUITY",
            "account_name": "Previous-year accumulated earnings",
            "currency": data.currency,
            "previous_closing": fixed(before),
            "next_opening": fixed(after),
            "difference": fixed(after - before),
            "reconciled": before == after,
            "derived": True,
        }
    )
    difference = sum((abs(money(row["difference"])) for row in rows), Decimal(0))
    accounts = [row for row in rows if row["row_kind"] == "ACCOUNT_CONTINUITY"]
    control = {
        "row_kind": "CONTINUITY_CONTROL",
        "previous_year_id": prior["id"],
        "next_year_id": target["id"],
        "previous_year_code": prior["code"],
        "next_year_code": target["code"],
        "previous_closing_date": prior["end_date"],
        "next_opening_date": target["start_date"],
        "currency": data.currency,
        "difference": fixed(difference),
        "reconciled": difference == 0,
        "account_count": len(accounts),
        "bill_count": sum(row["row_kind"] == "BILL_CONTINUITY" for row in rows),
        "advance_count": sum(row["row_kind"] == "ADVANCE_CONTINUITY" for row in rows),
        "previous_debit": fixed(
            sum((max(money(row["previous_closing"]), Decimal(0)) for row in accounts), Decimal(0))
        ),
        "previous_credit": fixed(
            sum((max(-money(row["previous_closing"]), Decimal(0)) for row in accounts), Decimal(0))
        ),
        "next_debit": fixed(
            sum((max(money(row["next_opening"]), Decimal(0)) for row in accounts), Decimal(0))
        ),
        "next_credit": fixed(
            sum((max(-money(row["next_opening"]), Decimal(0)) for row in accounts), Decimal(0))
        ),
    }
    return [control, *rows]
