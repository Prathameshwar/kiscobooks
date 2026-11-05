"""Fiscal anchor validation shared by create and merged partial updates."""

import datetime as dt


def validate_fiscal_anchor(month: int, day: int) -> None:
    try:
        dt.date(2000, month, day)  # Leap-day anchors are supported; impossible dates are not.
    except ValueError as exc:
        raise ValueError(
            "Choose a valid fiscal start month and day (for example, 1 April)."
        ) from exc
