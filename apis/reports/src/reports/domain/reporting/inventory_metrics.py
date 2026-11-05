"""Exact full-result metrics without adding running balances or audit rows."""

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any


def balances(code: str, rows: list[dict[str, Any]], currency: str) -> dict[str, Any]:
    keys = ("opening", "inward", "outward", "quantity", "eligible", "reserved", "available")
    values: dict[tuple[str, str, str], dict[str, Decimal | None]] = {}
    owned_value: Decimal | None = Decimal(0)
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for row in rows:
            key = (row["unit"], row["owner"], row["custody"])
            bucket = values.setdefault(key, {})
            for name in keys:
                if name not in row:
                    continue
                previous = bucket.get(name, Decimal(0))
                value = row[name]
                bucket[name] = (
                    None if previous is None or value is None else previous + Decimal(value)
                )
            if row["owner"] == "OWN":
                value = row.get("carrying_value")
                owned_value = (
                    None if value is None or owned_value is None else owned_value + Decimal(value)
                )
    return {
        "code": code,
        "row_count": len(rows),
        "item_count": len({r["item_id"] for r in rows if r.get("item_id")}),
        "location_count": len({r["location_id"] for r in rows if r.get("location_id")}),
        "currency": currency,
        "owned_value": format(owned_value, ".4f") if owned_value is not None else None,
        "quantities": [
            {
                "unit": key[0],
                "owner": key[1],
                "custody": key[2],
                **{
                    name: format(value, ".4f") if value is not None else None
                    for name, value in bucket.items()
                },
            }
            for key, bucket in sorted(values.items())
        ],
    }


def ledger(rows: list[dict[str, Any]], currency: str) -> dict[str, Any]:
    opening: dict[str, dict[str, Any]] = {}
    closing: dict[str, dict[str, Any]] = {}
    movements = []
    for row in rows:
        identity = row["position_id"]
        closing[identity] = row
        if row["row_kind"] == "OPENING":
            opening[identity] = row
        else:
            movements.append(row)
    values: dict[tuple[str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: dict.fromkeys(("opening", "inward", "outward", "quantity"), Decimal(0))
    )
    owned_value: Decimal | None = Decimal(0)
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for identity, row in closing.items():
            bucket = values[(row["unit"], row["owner"], row["custody"])]
            bucket["opening"] += Decimal(opening[identity]["balance"])
            bucket["quantity"] += Decimal(row["balance"])
            if row["owner"] == "OWN":
                value = row.get("value_balance")
                owned_value = (
                    None if owned_value is None or value is None else owned_value + Decimal(value)
                )
        for row in movements:
            bucket = values[(row["unit"], row["owner"], row["custody"])]
            for key in ("inward", "outward"):
                bucket[key] += Decimal(row[key])
    return {
        "code": "ITEM_LEDGER",
        "row_count": len(rows),
        "item_count": len({row["item_id"] for row in rows}),
        "entry_count": len(movements),
        "owned_value": format(owned_value, ".4f") if owned_value is not None else None,
        "currency": currency,
        "quantities": [
            {
                "unit": key[0],
                "owner": key[1],
                "custody": key[2],
                **{name: format(value, ".4f") for name, value in bucket.items()},
            }
            for key, bucket in sorted(values.items())
        ],
    }
