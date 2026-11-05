"""Readable accounting controls with a separate retained-source projection."""

from reports.domain.reporting.contracts import Column, View

CONTROLS = {
    "BALANCE_CONTINUITY": (
        "Year continuity",
        (
            "row_kind",
            "account_name",
            "reference",
            "currency",
            "previous_closing",
            "next_opening",
            "difference",
            "reconciled",
        ),
    ),
    "SOURCE_RECONCILIATION": (
        "Snapshot controls",
        ("kind", "source", "count", "currency", "DEBIT", "CREDIT"),
    ),
    "INVOICE_GL_BRIDGE": (
        "Posted invoice effects",
        (
            "period",
            "posting_date",
            "bill_reference",
            "account_code",
            "account_name",
            "side",
            "currency",
            "amount",
        ),
    ),
}


def registered_controls(code: str, output: tuple[Column, ...]) -> tuple[View, ...] | None:
    if code not in CONTROLS:
        return None
    title, keys = CONTROLS[code]
    columns = {column.key: column for column in output}
    views: tuple[View, ...] = (
        View("default", title, tuple(columns[key] for key in keys), "RECONCILIATION"),
    )
    if code != "SOURCE_RECONCILIATION":
        views += (View("source", "Source details", output, "RECONCILIATION"),)
    return views
