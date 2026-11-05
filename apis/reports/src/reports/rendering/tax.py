"""Readable metadata for exports of recorded tax, credit and GL evidence."""

from typing import Any

from billing_platform.display import DisplayConfiguration, date, number


def _amount_label(key: str) -> str:
    return " ".join("RCM" if word.upper() == "RCM" else word.title() for word in key.split("_"))


def metadata(
    evidence: dict[str, Any], parameters: dict[str, Any], display: DisplayConfiguration
) -> tuple[tuple[str, str], ...]:
    summary = evidence["tax_summary"]
    values = [
        (
            "Period",
            date(parameters["date_from"], display) + " to " + date(parameters["date_to"], display),
        ),
        (
            "Date basis",
            {
                "POSTING": "Posting date",
                "DOCUMENT": "Document date",
                "TAX_POINT": "Recorded tax point",
            }.get(parameters.get("date_basis", "POSTING"), "Posting date"),
        ),
        ("Source", "Verified recorded tax and posted ledger evidence"),
        ("Scope", "Recorded-tax report; statutory return submission is separate"),
    ]
    if summary["code"] == "INVOICE_TAX_REGISTER":
        values.append(
            (
                "Taxable value",
                "Each supply counted once across its tax components; "
                "notes reduce their original direction",
            )
        )
    if summary["code"] == "INVOICE_CREDIT_REGISTER":
        values.append(
            (
                "Credit events" if summary.get("mode") == "EVENTS" else "Credit positions",
                "Committed events in the selected period; action amounts remain separate"
                if summary.get("mode") == "EVENTS"
                else "Closing positions as of the To date; "
                "events are period activity and not added to positions",
            )
        )
    if summary["code"] == "TAX_GL_BRIDGE":
        values.append(
            (
                "Ledger net",
                "Debit less credit is tax-account movement, not a reconciliation mismatch",
            )
        )
    if summary.get("comparison_present"):
        values.append(("Totals basis", "Current period; comparative rows are shown separately"))
    selected_amounts = (
        summary.get("event_amounts", {}) if summary.get("mode") == "EVENTS" else summary["amounts"]
    )
    for currency, amounts in selected_amounts.items():
        values.append(
            (
                currency,
                "; ".join(
                    _amount_label(key) + " " + number(value, display)
                    for key, value in amounts.items()
                ),
            )
        )
    return tuple(values)
