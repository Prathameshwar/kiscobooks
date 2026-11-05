"""Buyer/product gross profit from matched commercial lines and actual stock costs."""

from collections import defaultdict
from decimal import localcontext
from typing import Any

from reports.domain.analytics_common import ZERO, line_details, percent, periods, summary
from reports.domain.reconcile import fixed, money


def hierarchy(stock: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, str]]:
    ancestors: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for identity in stock["groups"]:
        chain: list[str] = []
        names: list[str] = []
        cursor = identity
        while cursor:
            if cursor in chain or cursor not in stock["groups"] or len(chain) >= 64:
                raise ValueError("inventory group hierarchy is cyclic or incomplete")
            chain.append(cursor)
            group = stock["groups"][cursor]
            names.append(group["name"])
            cursor = group.get("parent_id")
        ancestors[identity] = set(chain)
        labels[identity] = " / ".join(reversed(names))
    return {
        identity: set().union(*(ancestors[group] for group in item["group_ids"]))
        for identity, item in stock["items"].items()
    }, labels


def dimensions(
    code: str,
    view: str,
    line: dict[str, Any],
    buyer: str,
    memberships: dict[str, set[str]],
    labels: dict[str, str],
) -> list[dict[str, Any]]:
    if code == "BUYER_PROFIT":
        return [
            {
                "identity": line["invoice_id"]
                if view == "invoices"
                else line["party_id"] or "unidentified",
                "label": line["bill_reference"]
                if view == "invoices"
                else buyer
                if line["party_id"]
                else "Unidentified buyer",
                "party_id": line["party_id"],
                **(
                    {
                        key: line[key]
                        for key in (
                            "invoice_id",
                            "invoice_kind",
                            "posting_date",
                            "bill_reference",
                            "account_name",
                        )
                    }
                    if view == "invoices"
                    else {}
                ),
            }
        ]
    item = line["item_id"]
    unmapped = "Unmapped " + line["supply_kind"].lower() + " lines"
    if view == "groups":
        groups = memberships.get(item, set())
        return (
            [
                {"identity": group, "group_id": group, "label": labels[group]}
                for group in sorted(groups)
            ]
            if groups
            else [
                {
                    "identity": "ungrouped" if item else "unmapped:" + line["supply_kind"],
                    "group_id": None,
                    "label": "Ungrouped products" if item else unmapped,
                }
            ]
        )
    return [
        {
            "identity": item or "unmapped:" + line["supply_kind"],
            "item_id": item,
            "label": line["item_name"] if item else unmapped,
            "unit": line["unit"],
        }
    ]


def totals(lines: list[dict[str, Any]]) -> dict[str, Any]:
    sales = sum((money(line["net_sales"]) for line in lines), ZERO)
    missing = sum(line["cost"] is None for line in lines)
    cost = None if missing else sum((money(line["cost"]) for line in lines), ZERO)
    profit = sales - cost if cost is not None else None
    return {
        "net_sales": fixed(sales),
        "cost": fixed(cost) if cost is not None else None,
        "gross_profit": fixed(profit) if profit is not None else None,
        "margin_percent": percent(profit, sales) if profit is not None else None,
        "cost_status": "COST_UNAVAILABLE" if missing else "VERIFIED",
        "unavailable_line_count": missing,
        "invoice_count": len(
            {line["invoice_id"] for line in lines if line["invoice_kind"] == "SALES"}
        ),
        "return_count": len(
            {line["invoice_id"] for line in lines if line["invoice_kind"] == "CREDIT_NOTE"}
        ),
    }


def compare(rows: list[dict[str, Any]], unmapped_prior: set[str]) -> None:
    previous = {
        (row["currency"], row["identity"]): row for row in rows if row["period"] == "COMPARATIVE"
    }
    for row in rows:
        if row["period"] != "CURRENT":
            continue
        prior = previous.get((row["currency"], row["identity"]))
        original = (
            (None if row["currency"] in unmapped_prior else ZERO)
            if prior is None
            else money(prior["gross_profit"])
            if prior["gross_profit"] is not None
            else None
        )
        current = money(row["gross_profit"]) if row["gross_profit"] is not None else None
        change = current - original if current is not None and original is not None else None
        row.update(
            comparison_amount=fixed(original) if original is not None else None,
            change_amount=fixed(change) if change is not None else None,
            change_percent=percent(change, original)
            if change is not None and original is not None
            else None,
        )


def calculate(
    code: str,
    documents: list[dict[str, Any]],
    values: dict[str, Any],
    stock: dict[str, Any],
    *,
    view: str = "default",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if code not in {"BUYER_PROFIT", "PRODUCT_PROFIT"} or view not in (
        {"default", "invoices"} if code == "BUYER_PROFIT" else {"default", "groups"}
    ):
        raise ValueError("unsupported dimension profit report view")
    rows: list[dict[str, Any]] = []
    amounts: dict[str, Any] = {}
    buyers = {
        document["invoice_id"]: (document.get("customer_name") or document["account_name"])
        if document["party_id"]
        else "Unidentified buyer"
        for document in documents
    }
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        lines = line_details(documents, stock)
    memberships, labels = hierarchy(stock) if code == "PRODUCT_PROFIT" else ({}, {})
    search = str(values.get("search") or "").casefold()
    notices = [
        "Gross profit is commercial net sales excluding GST, less matching actual stock cost. "
        "Credit notes reverse both sales and their recorded return cost.",
        "Shared overheads, company P&L and imported opening aggregates are not allocated to "
        "buyers or products. These figures are gross profit, not company net profit.",
        "Amounts stay separate by document currency. Costs require complete matching evidence "
        "in that currency; no FX estimates or latest purchase prices are used.",
        "Filters apply to both rows and summary totals. Comparison amounts refer to gross "
        "profit; an unavailable prior cost is not treated as zero.",
    ]
    if code == "PRODUCT_PROFIT":
        notices.append(
            "Product groups include descendants and use the frozen inventory hierarchy. "
            "Overlapping and parent/child group rows are not additive; summary totals count "
            "each source line once."
        )
        if any(line["item_id"] is None for line in lines):
            notices.append(
                "Product identity is unavailable for lines without a matching retained stock "
                "movement. Unmapped lines remain visible separately and are excluded when a "
                "specific product or group is selected."
            )
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for period, begin, end in periods(values):
            selected = [
                line
                for line in lines
                if begin <= line["posting_date"] <= end
                and (not values.get("currency") or line["currency"] == values["currency"])
                and (not values.get("party_id") or line["party_id"] == values["party_id"])
                and (not values.get("item_id") or line["item_id"] == values["item_id"])
                and (
                    not values.get("group_id")
                    or values["group_id"] in memberships.get(line["item_id"], set())
                )
            ]
            currencies: dict[str, list[dict[str, Any]]] = defaultdict(list)
            groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            dimension_rows: dict[tuple[str, str], dict[str, Any]] = {}
            for line in selected:
                choices = dimensions(
                    code, view, line, buyers[line["invoice_id"]], memberships, labels
                )
                choices = [
                    choice
                    for choice in choices
                    if not search
                    or search
                    in (
                        buyers[line["invoice_id"]] + " " + line["bill_reference"]
                        if code == "BUYER_PROFIT"
                        else choice["label"]
                    ).casefold()
                ]
                if choices:
                    currencies[line["currency"]].append(line)
                for choice in choices:
                    key = (line["currency"], choice["identity"])
                    groups[key].append(line)
                    dimension_rows[key] = choice
            amounts[period] = {
                currency: totals(items) for currency, items in sorted(currencies.items())
            }
            for (currency, identity), items in sorted(groups.items()):
                invoices = {item["invoice_id"] for item in items}
                rows.append(
                    {
                        "row_kind": "INVOICE_PROFIT"
                        if view == "invoices"
                        else "GROUP_PROFIT"
                        if view == "groups"
                        else code,
                        "period": period,
                        "currency": currency,
                        **dimension_rows[(currency, identity)],
                        **totals(items),
                        **(
                            {
                                "_sales_invoice_id": next(iter(invoices))
                                if len(invoices) == 1
                                else None,
                                "_sales_complete_buyer": not search
                                or search in buyers[items[0]["invoice_id"]].casefold(),
                            }
                            if code == "BUYER_PROFIT"
                            else {}
                        ),
                    }
                )
        if len(periods(values)) == 2:
            # An absent product/group row is not evidence of zero prior activity
            # when some earlier invoices could not be assigned to any product.
            # Check before item/group/search filters discard those unmapped lines.
            unmapped_prior = {
                line["currency"]
                for line in lines
                if code == "PRODUCT_PROFIT"
                and line["item_id"] is None
                and values["comparative_from"] <= line["posting_date"] <= values["comparative_to"]
                and (not values.get("currency") or line["currency"] == values["currency"])
                and (not values.get("party_id") or line["party_id"] == values["party_id"])
            }
            compare(rows, unmapped_prior)
            if unmapped_prior:
                notices.append(
                    "Some comparative sales cannot be mapped to products. Missing product/group "
                    "comparison profit is unavailable rather than assumed to be zero."
                )
    if any(row["cost_status"] == "COST_UNAVAILABLE" for row in rows):
        notices.append(
            "Some lines lack complete matching cost evidence. Their cost and gross profit, "
            "and any totals containing them, are unavailable."
        )
    return rows, summary(code, values, amounts, notices=notices, view=view, row_count=len(rows)) | {
        "row_count": len(rows)
    }
