"""Sales drivers count documents once and keep product amounts at supply grain."""

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from reports.domain.analytics_common import (
    ZERO,
    average,
    comparison,
    date_bucket,
    line_details,
    matches,
    percent,
    periods,
    summary,
)
from reports.domain.reconcile import fixed, money


def aggregate(documents: list[dict[str, Any]], period: str, grain: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[(document["currency"], date_bucket(document["posting_date"], grain))].append(
            document
        )
    return [
        figures(rows) | {"period": period, "date": day, "label": day}
        for (currency, day), rows in sorted(groups.items())
    ]


def figures(documents: list[dict[str, Any]]) -> dict[str, Any]:
    sales = sum(
        (money(row["commercial_total"]) for row in documents if row["invoice_kind"] == "SALES"),
        ZERO,
    )
    returns = sum(
        (
            money(row["commercial_total"])
            for row in documents
            if row["invoice_kind"] == "CREDIT_NOTE"
        ),
        ZERO,
    )
    discounts = -sum(
        (
            (Decimal(-1) if row["invoice_kind"] == "CREDIT_NOTE" else Decimal(1))
            * money(component["amount"])
            for row in documents
            for component in row["components"]
            if component["purpose"] == "DISCOUNT"
        ),
        ZERO,
    )
    count = sum(row["invoice_kind"] == "SALES" for row in documents)
    return {
        "currency": documents[0]["currency"],
        "gross_sales": fixed(sales),
        "returns": fixed(returns),
        "net_sales": fixed(sales - returns),
        "discounts": fixed(discounts),
        "invoice_count": count,
        "return_count": sum(row["invoice_kind"] == "CREDIT_NOTE" for row in documents),
        "average_invoice": average(sales, count),
        "return_rate": percent(returns, sales),
    }


def calculate(
    documents: list[dict[str, Any]],
    values: dict[str, Any],
    stock: dict[str, Any],
    *,
    view: str = "default",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = []
    totals: dict[str, dict[str, Any]] = {}
    trends = []
    notices = [
        "Commercial sales exclude GST and already include invoice discounts. "
        "Returns are deducted once.",
        "Amounts are separate by document currency; "
        "average invoice uses sales invoices before returns.",
    ]
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for period, begin, end in periods(values):
            selected = [
                row
                for row in documents
                if begin <= row["posting_date"] <= end
                and matches(
                    row, values | {"search": ""} if view in {"products", "categories"} else values
                )
            ]
            currencies: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in selected:
                currencies[row["currency"]].append(row)
            totals[period] = {
                currency: figures(rows) for currency, rows in sorted(currencies.items())
            }
            trends.extend(aggregate(selected, period, values.get("grain", "MONTH")))
            if view == "periods":
                result.extend(aggregate(selected, period, values.get("grain", "MONTH")))
            elif view == "invoices":
                for row in selected:
                    result.append(
                        {
                            **{
                                key: row[key]
                                for key in (
                                    "invoice_id",
                                    "party_id",
                                    "party_account_id",
                                    "account_name",
                                    "bill_reference",
                                    "posting_date",
                                    "currency",
                                    "invoice_kind",
                                )
                            },
                            "period": period,
                            "label": row["bill_reference"],
                            "net_sales": fixed(
                                money(row["commercial_total"])
                                * (-1 if row["invoice_kind"] == "CREDIT_NOTE" else 1)
                            ),
                            "row_kind": "INVOICE",
                        }
                    )
            elif view in {"products", "categories"}:
                lines = line_details(selected, stock)
                grouped: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
                for line in lines:
                    label = (
                        line["supply_kind"]
                        if view == "categories"
                        else line["item_name"]
                        if line["item_id"]
                        else "Unmapped " + line["supply_kind"].lower() + " lines"
                    )
                    identity = (
                        line["supply_kind"]
                        if view == "categories"
                        else line["item_id"] or line["supply_kind"]
                    )
                    if not matches(line | {"label": label}, values):
                        continue
                    grouped[
                        (line["currency"], identity, line["unit"] if view == "products" else None)
                    ].append(line | {"label": label})
                for (currency, _identity, unit), items in sorted(
                    grouped.items(), key=lambda pair: str(pair[0])
                ):
                    amount = sum((money(item["net_sales"]) for item in items), ZERO)
                    result.append(
                        {
                            "period": period,
                            "currency": currency,
                            "label": items[0]["label"],
                            "category": items[0]["supply_kind"],
                            "item_id": items[0]["item_id"] if view == "products" else None,
                            "unit": unit,
                            "quantity": fixed(
                                sum((money(item["quantity"]) for item in items), ZERO)
                            )
                            if unit and all(item["quantity"] is not None for item in items)
                            else None,
                            "net_sales": fixed(amount),
                            "invoice_count": len(
                                {
                                    item["invoice_id"]
                                    for item in items
                                    if item["invoice_kind"] == "SALES"
                                }
                            ),
                            "contribution_percent": percent(
                                amount, money(totals[period][currency]["net_sales"])
                            ),
                        }
                    )
                notices.append(
                    "Product/category search filters breakdown rows. Totals and trends retain "
                    "all invoices in the applied period and document currency."
                )
                if any(line["supply_kind"] == "GOODS" and not line["item_id"] for line in lines):
                    notices.append(
                        "Some goods lack verified common-line stock links or matching "
                        "movement coverage; their revenue remains in unmapped goods."
                    )
            else:
                customers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
                for row in selected:
                    customers[(row["currency"], row["party_id"] or "UNIDENTIFIED")].append(row)
                for (currency, party), rows in sorted(customers.items()):
                    result.append(
                        figures(rows)
                        | {
                            "period": period,
                            "label": rows[0].get("customer_name") or rows[0]["account_name"]
                            if party != "UNIDENTIFIED"
                            else "Unidentified customers",
                            "party_id": None if party == "UNIDENTIFIED" else party,
                            "contribution_percent": percent(
                                money(figures(rows)["net_sales"]),
                                money(totals[period][currency]["net_sales"]),
                            ),
                        }
                    )
        if len(periods(values)) == 2 and view not in {"periods", "invoices"}:
            comparison(result, ("currency", "label", "party_id", "item_id", "unit"), "net_sales")
    for row in result:
        row.setdefault("row_kind", "BREAKDOWN")
    return result, summary(
        "SALES_PERFORMANCE",
        values,
        totals,
        notices=list(dict.fromkeys(notices)),
        trends=trends,
        view=view,
        row_count=len(result),
    ) | {"row_count": len(result)}
