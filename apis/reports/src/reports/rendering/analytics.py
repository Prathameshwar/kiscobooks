"""Portable exports retain business totals, evidence limits and applied thresholds."""

from typing import Any

from billing_platform.display import DisplayConfiguration, date


def metadata(
    evidence: dict[str, Any], parameters: dict[str, Any], display: DisplayConfiguration
) -> tuple[tuple[str, str], ...]:
    summary = evidence["analytics"]
    result = [
        ("Date basis", "Posting date"),
        ("Calculation", str(summary["calculation_version"])),
        (
            "Rounding",
            "Money is exact to four decimals; derived ratios use half-even to four decimals",
        ),
    ]
    if parameters.get("comparative_from"):
        result.append(
            (
                "Comparison",
                date(parameters["comparative_from"], display)
                + " to "
                + date(parameters["comparative_to"], display),
            )
        )
    for period, currencies in summary["amounts"].items():
        for currency, amounts in currencies.items():
            result.append(
                (
                    period.capitalize() + " " + currency,
                    "; ".join(
                        key.replace("_", " ")
                        + ": "
                        + ("Unavailable" if value is None else str(value))
                        for key, value in amounts.items()
                    ),
                )
            )
    for key in (
        "search",
        "segment",
        "inactive_days",
        "increase_percent",
        "material_amount",
        "due_within_days",
        "slow_stock_days",
    ):
        if parameters.get(key) is not None and parameters.get(key) != "":
            result.append((key.replace("_", " ").capitalize(), str(parameters[key])))
    if summary.get("inventory_as_of"):
        result.append(("Stock snapshot", date(summary["inventory_as_of"], display)))
    for key, title in (
        ("party_id", "Buyer"),
        ("item_id", "Product"),
        ("group_id", "Product group"),
        ("currency", "Document currency"),
    ):
        value = summary.get("selected_filters", {}).get(key)
        if value:
            result.append((title, str(value)))
    result.extend(("Interpretation", notice) for notice in summary["notices"])
    return tuple(result)
