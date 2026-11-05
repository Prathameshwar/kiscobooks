"""Clearing and statement reconciliation are append-only evidence, not new cash legs."""

import datetime as dt

from billing_platform.errors import ConflictError, ValidationFailedError


def next_event(
    previous: str,
    action: str,
    *,
    last_date: dt.date,
    date: dt.date,
    instrument_date: dt.date | None,
    reference: str | None,
) -> None:
    allowed = {
        "PRESENTED": {"BOOKED", "DISHONOURED"},
        "CLEARED": {"BOOKED", "PRESENTED"},
        "DISHONOURED": {"BOOKED", "PRESENTED"},
        "RECONCILED": {"CLEARED", "UNRECONCILED"},
        "UNRECONCILED": {"RECONCILED"},
    }
    if previous not in allowed.get(action, set()):
        raise ConflictError("bank event is not allowed in the current instrument state")
    if date < last_date:
        raise ValidationFailedError("bank event cannot precede its recorded history")
    if action == "CLEARED" and instrument_date and date < instrument_date:
        raise ValidationFailedError("clearing cannot precede the instrument date")
    if action == "RECONCILED" and not reference:
        raise ValidationFailedError("statement reference is required for reconciliation")
