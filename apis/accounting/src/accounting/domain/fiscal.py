"""Monthly calendars and legal period transitions; no framework or persistence."""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

from billing_platform.errors import ConflictError, ValidationFailedError


@dataclass(frozen=True, slots=True)
class PeriodSpan:
    sequence: int
    start_date: dt.date
    end_date: dt.date


def monthly_periods(start_year: int, month: int, day: int) -> tuple[PeriodSpan, ...]:
    """Anchor each month independently; short months clamp to their final day."""
    if not 1900 <= start_year <= 9997:
        raise ValidationFailedError("fiscal start year must be between 1900 and 9997")
    try:
        dt.date(2000, month, day)
    except ValueError as exc:
        raise ValidationFailedError("invalid fiscal calendar anchor") from exc
    boundaries = []
    for offset in range(13):
        year, zero_month = divmod(start_year * 12 + month - 1 + offset, 12)
        current_month = zero_month + 1
        boundaries.append(
            dt.date(year, current_month, min(day, calendar.monthrange(year, current_month)[1]))
        )
    return tuple(
        PeriodSpan(i + 1, boundaries[i], boundaries[i + 1] - dt.timedelta(days=1))
        for i in range(12)
    )


TRANSITIONS = {
    ("FUTURE", "OPEN"): "period.manage",
    ("OPEN", "SOFT_CLOSED"): "period.close",
    ("SOFT_CLOSED", "CLOSED"): "period.close",
    ("SOFT_CLOSED", "OPEN"): "period.reopen",
    ("CLOSED", "OPEN"): "period.reopen",
    ("CLOSED", "LOCKED"): "period.lock",
}


def transition_permission(before: str, after: str, preceding: tuple[str, ...]) -> str:
    permission = TRANSITIONS.get((before, after))
    if permission is None:
        raise ConflictError("fiscal period transition is not allowed")
    if after == "SOFT_CLOSED" and any(status in {"FUTURE", "OPEN"} for status in preceding):
        raise ConflictError("preceding fiscal periods must be soft closed first")
    if after in {"CLOSED", "LOCKED"} and any(
        status not in {"CLOSED", "LOCKED"} for status in preceding
    ):
        raise ConflictError("preceding fiscal periods must be closed first")
    return permission
