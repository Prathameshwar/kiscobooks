"""Human-readable metadata from the same frozen stock result being exported."""

from typing import Any

from billing_platform.display import DisplayConfiguration, date, number


def metadata(
    evidence: dict[str, Any],
    display: DisplayConfiguration,
    parameters: dict[str, Any] | None = None,
) -> tuple[tuple[str, str], ...]:
    summary, coverage = (
        evidence.get("stock_summary", evidence.get("inventory_metrics")),
        evidence["inventory_coverage"],
    )
    if summary is None:
        return (("As of", date(coverage["as_of"], display)),)
    parameters = parameters or {}
    start = parameters.get("date_from") or coverage["history_start"]
    values = [
        (
            "Movement window",
            date(start, display) + " to " + date(coverage["as_of"], display),
        ),
        ("Stock items", str(summary["item_count"])),
        (
            "Owned stock value",
            (number(summary["owned_value"], display) + " " + summary["currency"])
            if summary["owned_value"] is not None
            else "Unavailable",
        ),
        (
            "Reservations",
            "Verified"
            if coverage["reservations_complete"]
            else "Unavailable; available quantity cannot be certified",
        ),
        (
            "Valuation",
            "Verified owner carrying value"
            if coverage["valuation_complete"]
            else "Incomplete owner cost coverage",
        ),
        *summary.get("filters", {}).items(),
    ]
    if summary.get("code") in {"BATCH_SUMMARY", "STOCK_AGEING", "STOCK_REORDER"}:
        values = [value for value in values if value[0] != "Owned stock value"]
    if summary.get("code") == "STOCK_REORDER":
        values.extend(
            (
                (
                    "Stock quantity basis",
                    "Eligible stock; reservations are not deducted"
                    if parameters.get("quantity_basis") == "ELIGIBLE"
                    else "Available stock after reservations",
                ),
                (
                    "Stock bands",
                    "Company and warehouse bands can overlap; each suggestion has its own scope",
                ),
            )
        )
    if summary.get("code") == "STOCK_GROUP_SUMMARY":
        values.append(
            (
                "Overall totals",
                "Distinct physical positions; overlapping parent and child group rows "
                "are not additive",
            )
        )
    if summary.get("code") == "STOCK_AGEING":
        values.extend(
            (
                (
                    "Age from",
                    "Manufacture date"
                    if parameters.get("age_basis") == "MANUFACTURE"
                    else "Original receipt date",
                ),
                (
                    "Age bands (days)",
                    ", ".join(str(value) for value in parameters.get("buckets", (30, 60, 90, 180))),
                ),
            )
        )
    for bucket in summary["quantities"][:32]:
        label = (
            bucket["unit"]
            + " / "
            + ("Company owned" if bucket["owner"] == "OWN" else "Third party")
            + " / "
            + {"LOCAL": "In warehouse", "TRANSIT": "In transit", "EXTERNAL": "External custody"}[
                bucket["custody"]
            ]
        )
        values.append(
            (
                label,
                "; ".join(
                    key.title()
                    + " "
                    + (
                        number(bucket[key], display, quantity=True)
                        if bucket[key] is not None
                        else "Unavailable"
                    )
                    for key in ("opening", "inward", "outward", "quantity", "eligible", "available")
                    if key in bucket
                ),
            )
        )
    if len(summary["quantities"]) > 32:
        values.append(
            (
                "Further unit scopes",
                "Refer to the complete item rows; "
                "quantities in different base units are not additive",
            )
        )
    return tuple(values)
