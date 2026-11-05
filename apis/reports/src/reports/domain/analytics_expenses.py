"""Posted expenses and diagnostic commercial reductions stay independently reconciled."""

from collections import defaultdict
from decimal import localcontext
from typing import Any

from reports.domain.analytics_common import ZERO, comparison, matches, percent, periods, summary
from reports.domain.analytics_profit import figures
from reports.domain.analytics_sales import figures as sales_figures
from reports.domain.reconcile import fixed, money


def calculate(
    statements: list[dict[str, Any]],
    trends: list[dict[str, Any]],
    purchases: list[dict[str, Any]],
    values: dict[str, Any],
    currency: str,
    *,
    view: str = "default",
    sales_documents: list[dict[str, Any]] | None = None,
    stock: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    amounts: dict[str, Any] = {}
    notices = [
        (
            "Expenses use posted P&L classifications in company base currency. "
            "Search filters the breakdown; company totals retain the full period."
        ),
        (
            "Supplier purchases are commercial spending by document currency, "
            "including inventory or capital purchases. They are not added to "
            "expenses."
        ),
        (
            "Exceptions identify material spending changes for investigation; they "
            "do not establish waste or fraud. A comparison period is required to "
            "identify increases."
        ),
    ]
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for period, begin, end in periods(values):
            financial = [row for row in statements if row["period"] == period]
            metrics = figures(financial)
            expense = money(metrics["direct_costs"]) + money(metrics["operating_expenses"])
            amounts[period] = {
                currency: metrics
                | {
                    "total_expenses": fixed(expense),
                    "expense_income_percent": percent(expense, money(metrics["posted_income"])),
                }
            }
            accounts = [
                row
                for row in financial
                if row["row_kind"] == "EXPENSE"
                and money(row["amount"]) != ZERO
                and matches(row, values | {"search": ""} if view == "groups" else values)
            ]
            if view == "reductions":
                documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for item in sales_documents or []:
                    if begin <= item["posting_date"] <= end:
                        documents[item["currency"]].append(item)
                for denomination, items in sorted(documents.items()):
                    diagnostic = sales_figures(items)
                    for key, title in (
                        ("returns", "Sales returns"),
                        ("discounts", "Net recorded sales discounts"),
                    ):
                        if not matches({"label": title, "currency": denomination}, values):
                            continue
                        rows.append(
                            {
                                "row_kind": "COMMERCIAL_REDUCTION",
                                "period": period,
                                "currency": denomination,
                                "label": title,
                                "metric": key,
                                "amount": diagnostic[key],
                            }
                        )
            elif view == "writeoffs":
                coverage = stock["coverage"] if stock else None
                if (
                    stock is not None
                    and coverage
                    and coverage["movements_complete"]
                    and coverage["history_start"] <= begin
                    and end <= coverage["as_of"]
                ):
                    for movement in stock["movements"]:
                        position = stock["positions"][movement["position_id"]]
                        if (
                            begin <= movement["effective_date"] <= end
                            and position["owner"] == "OWN"
                            and movement["action"] in {"DISPOSAL", "COUNT"}
                            and money(movement["quantity_delta"]) < ZERO
                        ):
                            row = {
                                "row_kind": "STOCK_LOSS_DIAGNOSTIC",
                                "period": period,
                                "date": movement["effective_date"],
                                "item_id": movement["item_id"],
                                "label": stock["items"][movement["item_id"]]["name"],
                                "currency": coverage["currency"],
                                "action": movement["action"],
                                "amount": fixed(-money(movement["value_delta"]))
                                if movement["value_delta"] is not None
                                else None,
                            }
                            if matches(row, values):
                                rows.append(row)
            elif view == "suppliers":
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
                for item in purchases:
                    if begin <= item["posting_date"] <= end and matches(item, values):
                        grouped[(item["currency"], item["party_id"] or "UNIDENTIFIED")].append(item)
                for (denomination, party), items in sorted(grouped.items()):
                    bought = sum(
                        (
                            money(item["commercial_total"])
                            for item in items
                            if item["invoice_kind"] == "PURCHASE"
                        ),
                        ZERO,
                    )
                    returned = sum(
                        (
                            money(item["commercial_total"])
                            for item in items
                            if item["invoice_kind"] == "DEBIT_NOTE"
                        ),
                        ZERO,
                    )
                    rows.append(
                        {
                            "row_kind": "SUPPLIER_SPENDING",
                            "period": period,
                            "currency": denomination,
                            "party_id": None if party == "UNIDENTIFIED" else party,
                            "label": items[0]["customer_name"],
                            "amount": fixed(bought - returned),
                            "purchases": fixed(bought),
                            "purchase_returns": fixed(returned),
                            "invoice_count": sum(
                                item["invoice_kind"] == "PURCHASE" for item in items
                            ),
                        }
                    )
            elif view == "periods":
                for item in trends:
                    if item["period"] == period:
                        rows.append(
                            item
                            | {
                                "label": item["date"],
                                "amount": fixed(
                                    money(item["direct_costs"]) + money(item["operating_expenses"])
                                ),
                            }
                        )
            elif view == "groups":
                groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for item in accounts:
                    groups[item["group_id"]].append(item)
                for identity, items in sorted(groups.items()):
                    if not matches({"label": items[0]["group_name"]}, values):
                        continue
                    rows.append(
                        {
                            "row_kind": "EXPENSE_GROUP",
                            "period": period,
                            "currency": currency,
                            "group_id": identity,
                            "label": items[0]["group_name"],
                            "amount": fixed(sum((money(item["amount"]) for item in items), ZERO)),
                        }
                    )
            else:
                rows.extend(
                    item
                    | {
                        "period": period,
                        "label": item["account_name"],
                        "classification": "DIRECT_COST"
                        if item["affects_gross_profit"]
                        else "OPERATING_EXPENSE",
                    }
                    for item in accounts
                )
        if len(periods(values)) == 2 and view not in {"periods", "writeoffs"}:
            comparison(rows, ("currency", "account_id", "group_id", "party_id", "label"), "amount")
        material = money(values.get("material_amount", "1000"))
        threshold = money(str(values.get("increase_percent", 25)))
        for row in rows:
            row["exception"] = None
            if row["period"] == "CURRENT" and "comparison_amount" in row:
                prior, change = money(row["comparison_amount"]), money(row["change_amount"])
                if change >= material and change > ZERO:
                    if prior <= ZERO:
                        row["exception"] = "NEW_OR_RESUMED_SPENDING"
                    elif (
                        row["change_percent"] is not None
                        and money(row["change_percent"]) >= threshold
                    ):
                        row["exception"] = "MATERIAL_INCREASE"
        if view == "exceptions":
            rows = [row for row in rows if row["period"] == "CURRENT" and row["exception"]]
    expense_trends = [
        item | {"amount": fixed(money(item["direct_costs"]) + money(item["operating_expenses"]))}
        for item in trends
    ]
    notices.append(
        "Recorded sales reductions and stock-loss movements are diagnostics, already reflected "
        "in their source postings; they are not deducted from profit again. Stock losses require "
        "complete retained movement history."
    )
    if view == "writeoffs" and (
        not stock
        or not stock["coverage"]
        or not stock["coverage"]["movements_complete"]
        or any(
            begin < stock["coverage"]["history_start"] or end > stock["coverage"]["as_of"]
            for _, begin, end in periods(values)
        )
    ):
        notices.append(
            "Stock loss evidence is unavailable for this source. "
            "An empty breakdown does not establish that no losses occurred."
        )
    return rows, summary(
        "EXPENSE_PROFIT_LEAKAGE",
        values,
        amounts,
        notices=notices,
        trends=expense_trends,
        view=view,
        row_count=len(rows),
    ) | {"row_count": len(rows)}
