"""Exact, currency-separated business metrics over verified immutable inputs."""

from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError

from reports.domain.reconcile import fixed, money

ZERO = Decimal(0)
CALCULATION_VERSION = 3


def percent(numerator: Decimal, denominator: Decimal) -> str | None:
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        if denominator <= 0:
            return None
        value = numerator * 100 / denominator
        return (
            None
            if abs(value) >= Decimal("1000000000000000")
            else fixed(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
        )


def average(amount: Decimal, count: int) -> str | None:
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        return (
            None
            if not count
            else fixed((amount / count).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
        )


def periods(values: dict[str, Any]) -> list[tuple[str, str, str]]:
    result = [("CURRENT", values["date_from"], values["date_to"])]
    if values.get("comparative_from") and values.get("comparative_to"):
        result.append(("COMPARATIVE", values["comparative_from"], values["comparative_to"]))
    return result


def date_bucket(day: str, grain: str) -> str:
    return day if grain == "DAY" else day[:7] + "-01"


def matches(row: dict[str, Any], values: dict[str, Any]) -> bool:
    return (not values.get("currency") or row["currency"] == values["currency"]) and (
        not values.get("search")
        or values["search"].casefold()
        in " ".join(
            str(row.get(key) or "")
            for key in (
                "label",
                "account_name",
                "customer_name",
                "item_name",
                "reference",
                "bill_reference",
            )
        ).casefold()
    )


def comparison(rows: list[dict[str, Any]], keys: tuple[str, ...], amount: str) -> None:
    prior = {
        tuple(row.get(key) for key in keys): row
        for row in rows
        if row.get("period") == "COMPARATIVE"
    }
    for row in rows:
        if row.get("period") != "CURRENT":
            continue
        previous = prior.get(tuple(row.get(key) for key in keys))
        original = (
            money(previous[amount]) if previous and previous.get(amount) is not None else ZERO
        )
        current = money(row[amount]) if row.get(amount) is not None else None
        row["comparison_amount"] = fixed(original)
        row["change_amount"] = fixed(current - original) if current is not None else None
        row["change_percent"] = (
            percent(current - original, original) if current is not None else None
        )


def summary(
    code: str,
    values: dict[str, Any],
    amounts: dict[str, Any],
    *,
    notices: list[str] | None = None,
    trends: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "analytics": {
            "code": code,
            "calculation_version": CALCULATION_VERSION,
            "date_basis": "POSTING",
            "date_from": values["date_from"],
            "date_to": values["date_to"],
            "comparison_present": len(periods(values)) == 2,
            "amounts": amounts,
            "trends": trends or [],
            "notices": notices or [],
            **extra,
        }
    }


def stock_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate the full owner snapshot before using its dimensions or cost movements."""
    if not records:
        return {"coverage": None, "items": {}, "positions": {}, "movements": [], "groups": {}}
    from reports.domain.reporting.inventory import Inventory

    stock = Inventory(records)
    return {
        "coverage": stock.coverage.model_dump(mode="json"),
        "items": {key: value.model_dump(mode="json") for key, value in stock.items.items()},
        "positions": {key: value.model_dump(mode="json") for key, value in stock.positions.items()},
        "movements": [value.model_dump(mode="json") for value in stock.movements],
        "groups": {key: value.model_dump(mode="json") for key, value in stock.groups.items()},
    }


def line_details(documents: list[dict[str, Any]], stock: dict[str, Any]) -> list[dict[str, Any]]:
    by_line: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    references: dict[tuple[str, str], int] = defaultdict(int)
    for document in documents:
        for supply in document["supplies"]:
            references[(document["voucher_id"], str(supply.get("item_line_key")))] += 1
    for movement in stock["movements"]:
        if movement.get("line_id") and movement["action"] in {"SALE", "CUSTOMER_RETURN"}:
            by_line[(movement["voucher_id"], movement["line_id"])].append(movement)
    result = []
    for document in documents:
        sign = Decimal(-1) if document["invoice_kind"] == "CREDIT_NOTE" else Decimal(1)
        if sum((money(line["commercial"]) for line in document["supplies"]), ZERO) != money(
            document["commercial_total"]
        ):
            raise ConflictError("invoice commercial lines do not reconcile to their header")
        for line in document["supplies"]:
            movements = by_line.get((document["voucher_id"], str(line.get("item_line_key"))), [])
            coverage = stock["coverage"]
            valid = bool(
                movements
                and coverage
                and coverage["movements_complete"]
                and coverage["history_start"] <= document["posting_date"] <= coverage["as_of"]
                and all(
                    movement["effective_date"] == document["posting_date"] for movement in movements
                )
                and len({movement["item_id"] for movement in movements}) == 1
                and all(
                    movement["action"] == ("CUSTOMER_RETURN" if sign < 0 else "SALE")
                    for movement in movements
                )
            )
            item = stock["items"].get(movements[0]["item_id"]) if valid else None
            cost_known = bool(
                valid
                and coverage["valuation_complete"]
                and coverage["currency"] == document["currency"]
                and all(movement["value_delta"] is not None for movement in movements)
                and all(
                    stock["positions"][movement["position_id"]]["owner"] == "OWN"
                    for movement in movements
                )
                and references[(document["voucher_id"], str(line.get("item_line_key")))] == 1
            )
            cost = (
                -sum((money(movement["value_delta"]) for movement in movements), ZERO)
                if cost_known
                else None
            )
            amount = sign * money(line["commercial"])
            result.append(
                {
                    **{
                        key: document[key]
                        for key in (
                            "invoice_id",
                            "invoice_kind",
                            "party_id",
                            "account_name",
                            "currency",
                            "posting_date",
                            "bill_reference",
                        )
                    },
                    "source_id": line["id"],
                    "item_id": item["item_id"] if item else None,
                    "item_name": item["name"] if item else line["description"],
                    "category": line["supply_kind"] if not item else "PRODUCT",
                    "supply_kind": line["supply_kind"],
                    "unit": item["unit"] if item else None,
                    "quantity": fixed(
                        -sum((money(movement["quantity_delta"]) for movement in movements), ZERO)
                    )
                    if valid
                    and references[(document["voucher_id"], str(line.get("item_line_key")))] == 1
                    else None,
                    "net_sales": fixed(amount),
                    "cost": fixed(cost) if cost is not None else None,
                    "gross_profit": fixed(amount - cost) if cost is not None else None,
                    "cost_status": "VERIFIED" if cost_known else "COST_UNAVAILABLE",
                }
            )
    return result
