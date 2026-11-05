"""Exact, stable statement presentations over the frozen Profit and Loss rows."""

import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any

from billing_platform.errors import ConflictError

SECTIONS = (
    ("DIRECT_INCOME", "Direct income", "INCOME", True),
    ("DIRECT_EXPENSE", "Direct expenses", "EXPENSE", True),
    ("INDIRECT_INCOME", "Indirect income", "INCOME", False),
    ("INDIRECT_EXPENSE", "Indirect expenses", "EXPENSE", False),
)
TOTALS = frozenset({"TOTAL_INCOME", "TOTAL_EXPENSE", "GROSS_PROFIT", "NET_PROFIT"})


def exact(value: Any) -> Decimal:
    """A source amount is a finite, four-place decimal string; never round it here."""
    if not isinstance(value, str) or re.fullmatch(r"-?\d+\.\d{4}", value) is None:
        raise ConflictError("invalid Profit and Loss source amount")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ConflictError("invalid Profit and Loss source amount") from exc
    if not amount.is_finite():
        raise ConflictError("invalid Profit and Loss source amount")
    return amount


def present(
    source: list[dict[str, Any]], *, comparison: bool, show_zero: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Align periods by immutable account id and verify all published totals."""
    accounts: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    imported: dict[str, dict[str, Decimal]] = defaultdict(dict)
    totals: dict[str, dict[str, Decimal]] = defaultdict(dict)
    currency: str | None = None
    for row in source:
        period = row.get("period")
        if period not in {"CURRENT", "COMPARATIVE"}:
            raise ConflictError("invalid Profit and Loss period")
        if period == "COMPARATIVE" and not comparison:
            raise ConflictError("Profit and Loss view does not match its periods")
        if (
            not isinstance(row.get("currency"), str)
            or re.fullmatch(r"[A-Z]{3}", row["currency"]) is None
        ):
            raise ConflictError("invalid Profit and Loss currency")
        if currency is None:
            currency = row["currency"]
        elif currency != row["currency"]:
            raise ConflictError("Profit and Loss currency changed within a result")
        kind = row.get("row_kind")
        if kind in {"INCOME", "EXPENSE"}:
            key = str(row["account_id"])
            if key in accounts[period]:
                raise ConflictError("duplicate Profit and Loss account")
            exact(row["amount"])
            if "imported_ytd_amount" in row:
                imported[period][key] = exact(row["imported_ytd_amount"])
            accounts[period][key] = row
        elif kind in TOTALS:
            if kind in totals[period]:
                raise ConflictError("duplicate Profit and Loss total")
            totals[period][kind] = exact(row["amount"])
        else:
            raise ConflictError("unknown Profit and Loss source row")
    periods = ("CURRENT", "COMPARATIVE") if comparison else ("CURRENT",)
    if not currency or any(len(totals[period]) != 4 for period in periods):
        raise ConflictError("Profit and Loss totals are incomplete")

    def fixed(value: Decimal) -> str:
        return "0.0000" if value == 0 else format(value, ".4f")

    def visible(row: dict[str, Any], current: Decimal, previous: Decimal) -> bool:
        key = str(row["account_id"])
        return bool(
            current
            or previous
            or imported["CURRENT"].get(key, Decimal(0))
            or imported["COMPARATIVE"].get(key, Decimal(0))
        )

    def amounts(current: Decimal, previous: Decimal) -> dict[str, str | None]:
        result: dict[str, str | None] = {"amount": fixed(current)}
        if comparison:
            change = current - previous
            percentage = (
                None
                if previous == 0
                else format(
                    (change / abs(previous) * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    ".2f",
                )
                + "%"
            )
            result.update(
                previous_amount=fixed(previous),
                change_amount=fixed(change),
                change_percent=percentage,
            )
        return result

    with localcontext() as arithmetic:
        arithmetic.prec = 48
        buckets: dict[str, dict[str, list[tuple[dict[str, Any], Decimal, Decimal]]]] = {
            section: defaultdict(list) for section, *_ in SECTIONS
        }
        for key in sorted(
            set(accounts["CURRENT"]) | (set(accounts["COMPARATIVE"]) if comparison else set())
        ):
            current = accounts["CURRENT"].get(key)
            previous = accounts["COMPARATIVE"].get(key) if comparison else None
            representative = current or previous
            assert representative is not None
            if (
                current
                and previous
                and any(
                    current[field] != previous[field]
                    for field in (
                        "row_kind",
                        "account_code",
                        "account_name",
                        "group_id",
                        "group_code",
                        "group_name",
                        "affects_gross_profit",
                    )
                )
            ):
                raise ConflictError(
                    "Profit and Loss account classification changed between periods"
                )
            now = exact(current["amount"]) if current else Decimal(0)
            before = exact(previous["amount"]) if previous else Decimal(0)
            bucket = (
                "DIRECT_" if representative["affects_gross_profit"] else "INDIRECT_"
            ) + representative["row_kind"]
            buckets[bucket][str(representative["group_id"])].append((representative, now, before))

        output: list[dict[str, Any]] = []
        section_totals: dict[str, dict[str, str]] = {}
        for section, title, _, _ in SECTIONS:
            groups = buckets[section]
            now_total = sum((now for items in groups.values() for _, now, _ in items), Decimal(0))
            before_total = sum(
                (before for items in groups.values() for _, _, before in items), Decimal(0)
            )
            section_totals[section] = {"current": fixed(now_total), "previous": fixed(before_total)}
            output.append(
                {
                    "row_kind": "SECTION",
                    "section": section,
                    "label": title,
                    "currency": currency,
                    **amounts(now_total, before_total),
                }
            )
            for group_id, items in sorted(
                groups.items(), key=lambda pair: (pair[1][0][0]["group_code"], pair[0])
            ):
                group = items[0][0]
                group_now = sum((now for _, now, _ in items), Decimal(0))
                group_before = sum((before for _, _, before in items), Decimal(0))
                if show_zero or any(visible(row, now, before) for row, now, before in items):
                    output.append(
                        {
                            "row_kind": "GROUP",
                            "section": section,
                            "label": group["group_name"],
                            "group_id": group_id,
                            "group_code": group["group_code"],
                            "code": group["group_code"],
                            "currency": currency,
                            **amounts(group_now, group_before),
                        }
                    )
                for row, now, before in sorted(
                    items, key=lambda item: (item[0]["account_code"], str(item[0]["account_id"]))
                ):
                    if not show_zero and not visible(row, now, before):
                        continue
                    current_account = accounts["CURRENT"].get(str(row["account_id"]))
                    prior_account = (
                        accounts["COMPARATIVE"].get(str(row["account_id"])) if comparison else None
                    )
                    output.append(
                        {
                            "row_kind": "ACCOUNT",
                            "section": section,
                            "label": row["account_name"],
                            "account_id": row["account_id"],
                            "account_code": row["account_code"],
                            "code": row["account_code"],
                            "group_id": group_id,
                            "group_name": row["group_name"],
                            "currency": currency,
                            "imported_ytd_amount": current_account.get("imported_ytd_amount")
                            if current_account
                            else None,
                            "previous_imported_ytd_amount": prior_account.get("imported_ytd_amount")
                            if prior_account
                            else None,
                            **amounts(now, before),
                        }
                    )
            if section == "DIRECT_EXPENSE":
                output.append(
                    {
                        "row_kind": "GROSS_PROFIT",
                        "label": "Gross profit",
                        "currency": currency,
                        **amounts(
                            totals["CURRENT"]["GROSS_PROFIT"],
                            totals["COMPARATIVE"]["GROSS_PROFIT"] if comparison else Decimal(0),
                        ),
                    }
                )
        for period in periods:
            values = section_totals
            index = "current" if period == "CURRENT" else "previous"
            income = Decimal(values["DIRECT_INCOME"][index]) + Decimal(
                values["INDIRECT_INCOME"][index]
            )
            expense = Decimal(values["DIRECT_EXPENSE"][index]) + Decimal(
                values["INDIRECT_EXPENSE"][index]
            )
            gross = Decimal(values["DIRECT_INCOME"][index]) - Decimal(
                values["DIRECT_EXPENSE"][index]
            )
            if (
                income != totals[period]["TOTAL_INCOME"]
                or expense != totals[period]["TOTAL_EXPENSE"]
                or gross != totals[period]["GROSS_PROFIT"]
                or income - expense != totals[period]["NET_PROFIT"]
            ):
                raise ConflictError("Profit and Loss sections differ from authoritative totals")
        output.append(
            {
                "row_kind": "NET_PROFIT",
                "label": "Net profit",
                "currency": currency,
                **amounts(
                    totals["CURRENT"]["NET_PROFIT"],
                    totals["COMPARATIVE"]["NET_PROFIT"] if comparison else Decimal(0),
                ),
            }
        )
        summary = {
            "currency": currency,
            "sections": section_totals,
            "imported_ytd": {
                period: any("imported_ytd_amount" in row for row in accounts[period].values())
                for period in periods
            },
            "totals": {
                key: {
                    "current": fixed(totals["CURRENT"][key]),
                    "previous": fixed(totals["COMPARATIVE"][key]) if comparison else None,
                }
                for key in ("TOTAL_INCOME", "TOTAL_EXPENSE", "GROSS_PROFIT", "NET_PROFIT")
            },
        }
        return output, summary
