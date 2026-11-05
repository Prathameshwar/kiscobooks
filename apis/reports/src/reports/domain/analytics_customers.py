"""Observed customer activity with explicit history, inactivity and currency windows."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from reports.domain.analytics_common import (
    ZERO,
    average,
    comparison,
    matches,
    percent,
    periods,
    summary,
)
from reports.domain.analytics_sales import aggregate
from reports.domain.analytics_sales import figures as sales_figures
from reports.domain.reconcile import fixed, money


def calculate(
    documents: list[dict[str, Any]],
    values: dict[str, Any],
    coverage_start: str,
    *,
    view: str = "default",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results: list[dict[str, Any]] = []
    amounts: dict[str, Any] = {}
    trends: list[dict[str, Any]] = []
    unidentified_counts: dict[str, int] = {}
    threshold = values.get("inactive_days", 90)
    requested = values.get("segment", "ALL")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for period, begin, end in periods(values):
            cohort = {
                (row["currency"], row["party_id"]) for row in results if row["period"] == "CURRENT"
            }
            selected: list[dict[str, Any]] = []
            groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            unidentified = 0
            matching_parties = {
                (document["currency"], document["party_id"])
                for document in documents
                if matches(document, values)
            }
            for document in documents:
                if (
                    document["posting_date"] > end
                    or (document["currency"], document["party_id"]) not in matching_parties
                ):
                    continue
                if not document["party_id"]:
                    unidentified += begin <= document["posting_date"] <= end
                    continue
                groups[(document["currency"], document["party_id"])].append(document)
            for (currency, party), history in sorted(groups.items()):
                purchases = sorted(
                    (row for row in history if row["invoice_kind"] == "SALES"),
                    key=lambda row: (row["posting_date"], row["invoice_id"]),
                )
                current = [row for row in history if begin <= row["posting_date"] <= end]
                bought = [row for row in purchases if begin <= row["posting_date"] <= end]
                current_figures = (
                    sales_figures(current)
                    if current
                    else {
                        "net_sales": "0.0000",
                        "returns": "0.0000",
                        "invoice_count": 0,
                        "average_invoice": None,
                    }
                )
                first = purchases[0]["posting_date"] if purchases else None
                last = purchases[-1]["posting_date"] if purchases else None
                recency = (
                    (dt.date.fromisoformat(end) - dt.date.fromisoformat(last)).days
                    if last
                    else None
                )
                active = bool(bought)
                repeat = active and len(purchases) >= 2
                observed = bool(first and begin <= first <= end)
                inactive = recency is not None and recency >= threshold
                prior = [
                    row
                    for row in documents
                    if row["currency"] == currency
                    and row["party_id"] == party
                    and values.get("comparative_from", "9999")
                    <= row["posting_date"]
                    <= values.get("comparative_to", "0000")
                ]
                prior_amount = money(sales_figures(prior)["net_sales"]) if prior else ZERO
                declining = (
                    period == "CURRENT"
                    and len(periods(values)) == 2
                    and prior_amount > ZERO
                    and money(current_figures["net_sales"]) < prior_amount
                )
                flags = {
                    "ACTIVE": active,
                    "REPEAT": repeat,
                    "FIRST_OBSERVED": observed,
                    "INACTIVE": inactive,
                    "DECLINING": declining,
                }
                if requested != "ALL":
                    if (period == "CURRENT" and not flags[requested]) or (
                        period == "COMPARATIVE" and (currency, party) not in cohort
                    ):
                        continue
                row = {
                    "row_kind": "CUSTOMER",
                    "period": period,
                    "currency": currency,
                    "party_id": party,
                    "label": (purchases or history)[-1].get("customer_name")
                    or (purchases or history)[-1]["account_name"],
                    "net_sales": current_figures["net_sales"],
                    "purchase_count": len(bought),
                    "returns": current_figures["returns"],
                    "average_invoice": current_figures["average_invoice"],
                    "recorded_sales": sales_figures(history)["net_sales"],
                    "recorded_purchase_count": len(purchases),
                    "first_observed_date": first,
                    "last_purchase_date": last,
                    "days_since_purchase": recency,
                    "average_gap_days": average(
                        Decimal((dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days),
                        len(purchases) - 1,
                    )
                    if first and last and len(purchases) > 1
                    else None,
                    "segment": "NO_RETAINED_PURCHASE"
                    if not purchases
                    else "INACTIVE"
                    if inactive
                    else "DECLINING"
                    if declining
                    else "REPEAT"
                    if repeat
                    else "FIRST_OBSERVED"
                    if observed
                    else "ACTIVE"
                    if active
                    else "NO_PERIOD_PURCHASE",
                    "active": active,
                    "repeat": repeat,
                    "first_observed": observed,
                    "inactive": inactive,
                }
                results.append(row)
                selected.extend(current)
            currencies = sorted({row["currency"] for row in results if row["period"] == period})
            amounts[period] = {}
            for currency in currencies:
                customers = [
                    row
                    for row in results
                    if row["period"] == period and row["currency"] == currency
                ]
                active_count = sum(row["active"] for row in customers)
                repeat_count = sum(row["repeat"] for row in customers)
                positive = sum((max(ZERO, money(row["net_sales"])) for row in customers), ZERO)
                leaders = sorted(
                    (max(ZERO, money(row["net_sales"])) for row in customers), reverse=True
                )[:5]
                amounts[period][currency] = {
                    "net_sales": fixed(sum((money(row["net_sales"]) for row in customers), ZERO)),
                    "active_customers": active_count,
                    "repeat_customers": repeat_count,
                    "first_observed_customers": sum(row["first_observed"] for row in customers),
                    "inactive_customers": sum(row["inactive"] for row in customers),
                    "repeat_rate": percent(Decimal(repeat_count), Decimal(active_count)),
                    "top_five_share_percent": percent(sum(leaders, ZERO), positive),
                }
            trends.extend(aggregate(selected, period, values.get("grain", "MONTH")))
            unidentified_counts[period] = unidentified
        if len(periods(values)) == 2:
            comparison(results, ("currency", "party_id"), "net_sales")
    if view == "purchases":
        allowed = {(row["period"], row["currency"], row["party_id"]) for row in results}
        purchase_rows = []
        for period, begin, end in periods(values):
            for row in documents:
                if (period, row["currency"], row["party_id"]) in allowed and begin <= row[
                    "posting_date"
                ] <= end:
                    purchase_rows.append(
                        {
                            **{
                                key: row[key]
                                for key in (
                                    "invoice_id",
                                    "party_id",
                                    "account_name",
                                    "posting_date",
                                    "bill_reference",
                                    "currency",
                                    "invoice_kind",
                                )
                            },
                            "row_kind": "INVOICE",
                            "period": period,
                            "net_sales": fixed(
                                money(row["commercial_total"])
                                * (-1 if row["invoice_kind"] == "CREDIT_NOTE" else 1)
                            ),
                        }
                    )
        results = purchase_rows
    return results, summary(
        "CUSTOMER_INSIGHTS",
        values,
        amounts,
        trends=trends,
        notices=[
            "History begins "
            + coverage_start
            + ". First observed does not mean first ever; value is recorded sales, "
            "not predicted lifetime value.",
            f"Inactive means no purchase for at least {threshold} days as of each period end. "
            "Repeat means an active customer with at least two recorded sales invoices.",
            (
                "Customer counts and values are separate by currency. Top-five "
                "concentration uses positive net customer sales. Unidentified "
                "sales are excluded from customer segments."
            ),
            (
                "Segment filters select the current customer cohort; comparison "
                "retains those same customers."
            ),
            "Identified customers with returns but no retained purchase remain included. "
            "Their first/last purchase dates and inactivity are unknown.",
        ],
        inactive_days=threshold,
        segment=requested,
        unidentified_invoices=unidentified_counts,
        row_count=len(results),
        view=view,
    ) | {"row_count": len(results)}
