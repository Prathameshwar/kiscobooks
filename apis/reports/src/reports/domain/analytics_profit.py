"""Company profit reconciles to P&L; item margins require complete actual costs."""

from collections import defaultdict
from decimal import localcontext
from typing import Any

from reports.domain.analytics_common import (
    ZERO,
    comparison,
    line_details,
    matches,
    percent,
    periods,
    summary,
)
from reports.domain.reconcile import fixed, money


def figures(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        row["row_kind"]: money(row["amount"])
        for row in rows
        if row["row_kind"] not in {"INCOME", "EXPENSE"}
    }
    income = totals.get("TOTAL_INCOME", ZERO)
    expense = totals.get("TOTAL_EXPENSE", ZERO)
    direct_income = sum(
        (
            money(row["amount"])
            for row in rows
            if row["row_kind"] == "INCOME" and row["affects_gross_profit"]
        ),
        ZERO,
    )
    costs = sum(
        (
            money(row["amount"])
            for row in rows
            if row["row_kind"] == "EXPENSE" and row["affects_gross_profit"]
        ),
        ZERO,
    )
    gross = totals.get("GROSS_PROFIT", ZERO)
    net = totals.get("NET_PROFIT", ZERO)
    return {
        "posted_income": fixed(income),
        "direct_income": fixed(direct_income),
        "direct_costs": fixed(costs),
        "gross_profit": fixed(gross),
        "operating_expenses": fixed(expense - costs),
        "other_income": fixed(income - direct_income),
        "net_profit": fixed(net),
        "gross_margin_percent": percent(gross, direct_income),
        "net_margin_percent": percent(net, income),
    }


def calculate(
    statements: list[dict[str, Any]],
    trends: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    values: dict[str, Any],
    stock: dict[str, Any],
    base_currency: str,
    *,
    view: str = "default",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    amounts: dict[str, Any] = {}
    notices = [
        (
            "Company totals use posted base-currency P&L classifications. Direct "
            "costs and other income follow those classifications."
        ),
        (
            "Commercial invoice sales remain separate by document currency. No "
            "estimated FX or latest purchase price is used for margins."
        ),
        "Search filters breakdown rows; company P&L totals retain the complete selected period.",
    ]
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for period, begin, end in periods(values):
            financial = [row for row in statements if row["period"] == period]
            amounts[period] = {base_currency: figures(financial)}
            if view == "products":
                selected = [
                    row
                    for row in documents
                    if begin <= row["posting_date"] <= end and matches(row, values | {"search": ""})
                ]
                groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
                for item in line_details(selected, stock):
                    item = item | {
                        "label": item["item_name"]
                        if item["item_id"]
                        else "Unmapped " + item["supply_kind"].lower() + " lines"
                    }
                    if not matches(item, values):
                        continue
                    groups[
                        (item["currency"], item["item_id"] or item["supply_kind"], item["unit"])
                    ].append(item)
                for (currency, _identity, unit), items in sorted(
                    groups.items(), key=lambda pair: str(pair[0])
                ):
                    sales = sum((money(item["net_sales"]) for item in items), ZERO)
                    known = all(item["cost"] is not None for item in items)
                    cost = sum((money(item["cost"]) for item in items), ZERO) if known else None
                    rows.append(
                        {
                            "row_kind": "PRODUCT_MARGIN",
                            "period": period,
                            "currency": currency,
                            "label": items[0]["label"],
                            "item_id": items[0]["item_id"],
                            "unit": unit,
                            "net_sales": fixed(sales),
                            "cost": fixed(cost) if cost is not None else None,
                            "gross_profit": fixed(sales - cost) if cost is not None else None,
                            "margin_percent": percent(sales - cost, sales)
                            if cost is not None
                            else None,
                            "cost_status": "VERIFIED" if known else "COST_UNAVAILABLE",
                            "invoice_count": len(
                                {
                                    item["invoice_id"]
                                    for item in items
                                    if item["invoice_kind"] == "SALES"
                                }
                            ),
                        }
                    )
                if any(row["cost_status"] == "COST_UNAVAILABLE" for row in rows):
                    notices.append(
                        "Some product/service costs lack complete matching evidence. Their margin "
                        "is unavailable; company P&L remains independently calculated."
                    )
            elif view == "accounts":
                rows.extend(
                    {
                        **row,
                        "label": row["account_name"],
                        "period": period,
                    }
                    for row in financial
                    if row["row_kind"] in {"INCOME", "EXPENSE"}
                    and money(row["amount"]) != ZERO
                    and matches(row, values)
                )
            elif view == "periods":
                rows.extend(
                    row | {"label": row["date"]} for row in trends if row["period"] == period
                )
            else:
                metrics = amounts[period][base_currency]
                for key in (
                    "direct_income",
                    "direct_costs",
                    "gross_profit",
                    "operating_expenses",
                    "other_income",
                    "net_profit",
                ):
                    row = {
                        "row_kind": "PROFIT_DRIVER",
                        "period": period,
                        "currency": base_currency,
                        "label": key.replace("_", " ").capitalize(),
                        "metric": key,
                        "amount": metrics[key],
                    }
                    if matches(row, values):
                        rows.append(row)
        if len(periods(values)) == 2 and view != "periods":
            comparison(
                rows,
                ("currency", "metric", "account_id", "item_id", "unit", "label"),
                "net_sales" if view == "products" else "amount",
            )
    return rows, summary(
        "PROFIT_MARGIN_ANALYSIS",
        values,
        amounts,
        notices=list(dict.fromkeys(notices)),
        trends=trends,
        row_count=len(rows),
        view=view,
    ) | {"row_count": len(rows)}
