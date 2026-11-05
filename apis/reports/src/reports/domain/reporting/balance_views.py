"""Verified Balance Sheet presentations; all amounts come from frozen source rows."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError

from reports.domain.reporting.profit_views import exact

EARNINGS = {
    "OPENING_EARNINGS": "Opening earnings",
    "PRIOR_UNTRANSFERRED_EARNINGS": "Prior untransferred earnings",
    "CURRENT_YEAR_EARNINGS": "Current year earnings",
}
SECTIONS = {"ASSET": "Assets", "LIABILITY": "Liabilities", "EQUITY": "Equity"}


def present(
    source: list[dict[str, Any]], *, comparison: bool, show_zero: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    periods = ("CURRENT", "COMPARATIVE") if comparison else ("CURRENT",)
    accounts: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    earnings: dict[str, dict[str, Decimal]] = defaultdict(dict)
    controls: dict[str, dict[str, Decimal]] = {}
    currency = None
    for row in source:
        period, kind = row.get("period"), row.get("row_kind")
        if not isinstance(period, str) or period not in periods:
            raise ConflictError("Balance Sheet period differs from the view")
        if kind == "BALANCE_SHEET_CONTROL":
            if period in controls:
                raise ConflictError("duplicate Balance Sheet controls")
            controls[period] = {
                key: exact(row.get(key))
                for key in (
                    "assets",
                    "liabilities",
                    "equity",
                    "untransferred_earnings",
                    "difference",
                )
            }
            continue
        unit = row.get("currency")
        if (
            not isinstance(unit, str)
            or len(unit) != 3
            or not unit.isalpha()
            or not unit.isascii()
            or not unit.isupper()
        ):
            raise ConflictError("invalid Balance Sheet currency")
        if currency and currency != unit:
            raise ConflictError("Balance Sheet currency changed within its result")
        currency = unit
        exact(row.get("amount"))
        if kind == "ACCOUNT":
            identity = row.get("account_id")
            if not identity or identity in accounts[period] or row.get("nature") not in SECTIONS:
                raise ConflictError("invalid or duplicate Balance Sheet account")
            if any(
                not isinstance(row.get(key), str) or not row[key]
                for key in ("account_code", "account_name", "group_id", "group_code", "group_name")
            ):
                raise ConflictError("incomplete Balance Sheet account classification")
            accounts[period][str(identity)] = row
        elif kind in EARNINGS:
            if kind in earnings[period]:
                raise ConflictError("duplicate Balance Sheet earnings")
            earnings[period][kind] = exact(row["amount"])
        else:
            raise ConflictError("unknown Balance Sheet source row")
    if not currency or any(p not in controls or set(earnings[p]) != set(EARNINGS) for p in periods):
        raise ConflictError("Balance Sheet evidence is incomplete")

    def fixed(value: Decimal) -> str:
        return "0.0000" if value == 0 else format(value, ".4f")

    def amounts(now: Decimal, before: Decimal) -> dict[str, Any]:
        values: dict[str, Any] = {"amount": fixed(now)}
        if comparison:
            change = now - before
            values.update(
                previous_amount=fixed(before),
                change_amount=fixed(change),
                change_percent=None
                if before == 0
                else format(
                    (change / abs(before) * 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP),
                    ".2f",
                )
                + "%",
            )
        return values

    with localcontext() as arithmetic:
        arithmetic.prec = 48
        totals: dict[str, dict[str, Decimal]] = {}
        for period in periods:
            sums = {
                nature: sum(
                    (
                        exact(r["amount"])
                        for r in accounts[period].values()
                        if r["nature"] == nature
                    ),
                    Decimal(0),
                )
                for nature in SECTIONS
            }
            control = controls[period]
            earned = sum(earnings[period].values(), Decimal(0))
            if (
                any(
                    sums[k] != control[v]
                    for k, v in (
                        ("ASSET", "assets"),
                        ("LIABILITY", "liabilities"),
                        ("EQUITY", "equity"),
                    )
                )
                or earned != control["untransferred_earnings"]
                or control["difference"] != 0
                or sums["ASSET"] != sums["LIABILITY"] + sums["EQUITY"] + earned
            ):
                raise ConflictError("Balance Sheet presentation does not reconcile")
            totals[period] = sums | {
                "EQUITY": sums["EQUITY"] + earned,
                "LIABILITIES_EQUITY": sums["LIABILITY"] + sums["EQUITY"] + earned,
            }

        aligned: dict[str, dict[str, list[tuple[dict[str, Any], Decimal, Decimal]]]] = {
            key: defaultdict(list) for key in SECTIONS
        }
        group_labels: dict[str, tuple[str, str, str]] = {}
        for identity in sorted(set(accounts["CURRENT"]) | set(accounts["COMPARATIVE"])):
            current, previous = (
                accounts["CURRENT"].get(identity),
                accounts["COMPARATIVE"].get(identity),
            )
            representative = current or previous
            assert representative is not None
            row = representative
            if (
                current
                and previous
                and any(
                    current[key] != previous[key]
                    for key in (
                        "nature",
                        "account_code",
                        "account_name",
                        "group_id",
                        "group_code",
                        "group_name",
                    )
                )
            ):
                raise ConflictError("Balance Sheet classification changed between dates")
            group = row["group_id"]
            group_label = (row["nature"], row["group_code"], row["group_name"])
            if group in group_labels and group_labels[group] != group_label:
                raise ConflictError("Balance Sheet group classification is inconsistent")
            group_labels[group] = group_label
            aligned[row["nature"]][group].append(
                (
                    row,
                    exact(current["amount"]) if current else Decimal(0),
                    exact(previous["amount"]) if previous else Decimal(0),
                )
            )
        output: list[dict[str, Any]] = []
        for section, title in SECTIONS.items():
            side = "ASSETS" if section == "ASSET" else "LIABILITIES_EQUITY"
            common = {"section": section, "side": side, "currency": currency}
            now, before = (
                totals["CURRENT"][section],
                totals.get("COMPARATIVE", {}).get(section, Decimal(0)),
            )
            output.append(common | {"row_kind": "SECTION", "label": title, **amounts(now, before)})
            for group, items in sorted(
                aligned[section].items(), key=lambda pair: (group_labels[pair[0]][1], pair[0])
            ):
                if not show_zero and not any(now or before for _, now, before in items):
                    continue
                output.append(
                    common
                    | {
                        "row_kind": "GROUP",
                        "group_id": group,
                        "label": group_labels[group][2],
                        "code": group_labels[group][1],
                        "group_code": group_labels[group][1],
                        **amounts(
                            sum((now for _, now, _ in items), Decimal(0)),
                            sum((before for _, _, before in items), Decimal(0)),
                        ),
                    }
                )
                for row, now, before in sorted(
                    items, key=lambda item: (item[0]["account_code"], item[0]["account_id"])
                ):
                    if show_zero or now or before:
                        output.append(
                            common
                            | {
                                key: row[key]
                                for key in ("account_id", "account_code", "group_id", "group_name")
                            }
                            | {
                                "row_kind": "ACCOUNT",
                                "label": row["account_name"],
                                "code": row["account_code"],
                                **amounts(now, before),
                            }
                        )
            if section == "EQUITY":
                for key, label in EARNINGS.items():
                    output.append(
                        common
                        | {
                            "row_kind": "EARNINGS",
                            "label": label,
                            "derived": True,
                            **amounts(
                                earnings["CURRENT"][key],
                                earnings["COMPARATIVE"].get(key, Decimal(0)),
                            ),
                        }
                    )
            output.append(
                common
                | {
                    "row_kind": "TOTAL",
                    "label": "Total " + title.lower(),
                    **amounts(
                        totals["CURRENT"][section],
                        totals.get("COMPARATIVE", {}).get(section, Decimal(0)),
                    ),
                }
            )
        output.append(
            {
                "row_kind": "TOTAL",
                "section": "LIABILITIES_EQUITY",
                "side": "LIABILITIES_EQUITY",
                "currency": currency,
                "label": "Total liabilities and equity",
                **amounts(
                    totals["CURRENT"]["LIABILITIES_EQUITY"],
                    totals.get("COMPARATIVE", {}).get("LIABILITIES_EQUITY", Decimal(0)),
                ),
            }
        )
        return output, {
            "currency": currency,
            "balanced": True,
            "difference": {"current": "0.0000", "previous": "0.0000" if comparison else None},
            "totals": {
                key: {
                    "current": fixed(totals["CURRENT"][key]),
                    "previous": fixed(totals["COMPARATIVE"][key]) if comparison else None,
                }
                for key in totals["CURRENT"]
            },
        }
