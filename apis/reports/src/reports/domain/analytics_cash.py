"""Recorded cash, settlement-controlled obligations and dated owned stock remain separate."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from reports.domain.analytics_common import ZERO, comparison, matches, periods, summary
from reports.domain.reconcile import fixed, money


def signed(line: dict[str, Any]) -> Decimal:
    return money(line["base_amount"]) * (1 if line["side"] == "DEBIT" else -1)


def tied_stock(
    stock: dict[str, Any], end: str, days: int
) -> tuple[list[dict[str, Any]], str | None]:
    coverage = stock["coverage"]
    if not coverage or coverage["as_of"] != end or not coverage["valuation_complete"]:
        return [], None
    cutoff = (dt.date.fromisoformat(end) - dt.timedelta(days=days)).isoformat()
    rows = []
    for position in stock["positions"].values():
        if position["owner"] != "OWN" or money(position["quantity"]) <= ZERO:
            continue
        item = stock["items"][position["item_id"]]
        origins = position["origins"]
        complete = bool(
            coverage["origins_complete"]
            and origins
            and all(
                origin["provenance"] == "KNOWN" and origin["receipt_date"] for origin in origins
            )
        )
        old = complete and all(origin["receipt_date"] <= cutoff for origin in origins)
        demand = any(
            movement["item_id"] == position["item_id"]
            and movement["action"] in {"SALE", "CONSUMPTION"}
            and cutoff < movement["effective_date"] <= end
            for movement in stock["movements"]
        )
        history = coverage["movements_complete"] and coverage["history_start"] <= cutoff
        status = (
            "SLOW_MOVING"
            if old and history and not demand
            else "AGE_UNAVAILABLE"
            if not complete or not history
            else "RECENT_OR_MOVING"
        )
        rows.append(
            {
                "row_kind": "STOCK_TIED_UP",
                "label": item["name"],
                "item_id": position["item_id"],
                "position_id": position["position_id"],
                "quantity": position["quantity"],
                "unit": item["unit"],
                "amount": position["carrying_value"],
                "currency": coverage["currency"],
                "stock_status": status,
            }
        )
    return rows, fixed(sum((money(row["amount"]) for row in rows), ZERO))


def calculate(
    data: dict[str, Any],
    values: dict[str, Any],
    stock: dict[str, Any],
    currency: str,
    *,
    view: str = "default",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    amounts: dict[str, Any] = {}
    trends: list[dict[str, Any]] = []
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for period, begin, end in periods(values):
            source = data["periods"][period]
            balances: dict[str, dict[str, Any]] = {}
            for key, account in data["accounts"].items():
                selected = [line for line in source["lines"] if line["account_id"] == key]
                opening = sum(
                    (
                        signed(line)
                        for line in selected
                        if line["posting_date"] < begin
                        or (line["posting_date"] == begin and line["opening_effect"])
                    ),
                    ZERO,
                )
                closing = sum(
                    (signed(line) for line in selected if line["posting_date"] <= end), ZERO
                )
                balances[key] = {
                    "row_kind": "CASH_ACCOUNT",
                    "period": period,
                    "currency": currency,
                    "account_id": key,
                    "label": account["name"],
                    "account_name": account["name"],
                    "opening": fixed(opening),
                    "closing": fixed(closing),
                    "amount": fixed(closing),
                    "net_movement": fixed(closing - opening),
                }
            movements = source["movements"]
            receipts = sum((max(ZERO, money(row["amount"])) for row in movements), ZERO)
            payments = sum((max(ZERO, -money(row["amount"])) for row in movements), ZERO)
            opening = sum((money(row["opening"]) for row in balances.values()), ZERO)
            closing = sum((money(row["closing"]) for row in balances.values()), ZERO)
            # Later opening batches change balances without being receipts or payments.
            adjustment = closing - opening - receipts + payments
            debts = [row for row in source["bills"] if row["direction"] == "DEBT"]
            due_end = (
                dt.date.fromisoformat(end) + dt.timedelta(days=values.get("due_within_days", 30))
            ).isoformat()
            receivable = sum(
                (money(row["report_amount"]) for row in debts if row["role"] == "CUSTOMER"), ZERO
            )
            payable = sum(
                (money(row["report_amount"]) for row in debts if row["role"] == "SUPPLIER"), ZERO
            )
            overdue_customers = sum(
                (
                    money(row["report_amount"])
                    for row in debts
                    if row["role"] == "CUSTOMER" and row["due_date"] and row["due_date"] < end
                ),
                ZERO,
            )
            due_suppliers = sum(
                (
                    money(row["report_amount"])
                    for row in debts
                    if row["role"] == "SUPPLIER" and row["due_date"] and row["due_date"] <= due_end
                ),
                ZERO,
            )
            stock_rows, stock_value = tied_stock(stock, end, values.get("slow_stock_days", 90))
            if stock["coverage"] and stock["coverage"]["currency"] != currency:
                stock_rows, stock_value = [], None
            amounts[period] = {
                currency: {
                    "opening_cash": fixed(opening),
                    "cash_receipts": fixed(receipts),
                    "cash_payments": fixed(payments),
                    "cash_adjustments": fixed(adjustment),
                    "closing_cash": fixed(closing),
                    "receivables": fixed(receivable),
                    "payables": fixed(payable),
                    "overdue_receivables": fixed(overdue_customers),
                    "supplier_dues": fixed(due_suppliers),
                    "stock_tied_up": stock_value,
                    "slow_stock": fixed(
                        sum(
                            (
                                money(row["amount"])
                                for row in stock_rows
                                if row["stock_status"] == "SLOW_MOVING"
                            ),
                            ZERO,
                        )
                    )
                    if stock_value is not None
                    and all(row["stock_status"] != "AGE_UNAVAILABLE" for row in stock_rows)
                    else None,
                }
            }
            if view in {"customers", "suppliers"}:
                role = "CUSTOMER" if view == "customers" else "SUPPLIER"
                for item in source["bills"]:
                    if item["role"] == role:
                        rows.append(
                            item
                            | {
                                "period": period,
                                "label": item["account_name"],
                                "currency": currency,
                                "document_currency": item["currency"],
                                "amount": item["report_amount"],
                            }
                        )
            elif view == "stock":
                rows.extend(row | {"period": period} for row in stock_rows)
            elif view == "movements":
                rows.extend(
                    row
                    | {
                        "row_kind": "CASH_MOVEMENT",
                        "period": period,
                        "currency": currency,
                        "movement_kind": "INTERNAL_TRANSFER"
                        if money(row["amount"]) == ZERO
                        else "NET_RECEIPT"
                        if money(row["amount"]) > ZERO
                        else "NET_PAYMENT",
                    }
                    for row in movements
                )
            else:
                rows.extend(balances.values())
            grouped: dict[str, Any] = defaultdict(lambda: ZERO)
            for row in movements:
                grouped[row["date"][:7] + "-01"] += money(row["amount"])
            trends.extend(
                {"period": period, "date": date, "amount": fixed(amount), "currency": currency}
                for date, amount in sorted(grouped.items())
            )
        rows = [row for row in rows if matches(row, values)]
        if len(periods(values)) == 2 and view == "default":
            comparison(rows, ("account_id", "currency"), "closing")
    notices = [
        (
            "Cash/bank transfers are netted within each posted journal. Receipts "
            "and payments describe net recorded cash effects per journal, not a "
            "forecast. Opening adjustments are shown separately."
        ),
        (
            "Customer and supplier dues use as-of settlement-controlled base "
            "balances. Unapplied credits remain separate and are not treated as "
            "collected overdue debts."
        ),
        (
            "Owned stock uses the retained snapshot only when its date matches the "
            "report end date and currency matches the company base currency. Slow "
            "stock requires the entire position to have known old origins and no "
            "company-wide sale or consumption in the selected window, backed by "
            "complete movement history; missing evidence is unavailable."
        ),
        (
            "Search filters breakdown rows; cash and obligation totals retain the "
            "complete company period. Supplier dues include overdue bills and "
            "bills due within the selected horizon."
        ),
    ]
    return rows, summary(
        "CASH_WORKING_CAPITAL",
        values,
        amounts,
        notices=notices,
        trends=trends,
        view=view,
        row_count=len(rows),
    ) | {"row_count": len(rows)}
