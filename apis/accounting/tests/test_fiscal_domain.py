"""Calendar boundaries and terminal/sequential close semantics."""

import datetime as dt
from itertools import pairwise

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError

from accounting.domain.fiscal import monthly_periods, transition_permission


@pytest.mark.parametrize(
    "year,month,day", [(2026, 4, 1), (2024, 2, 29), (2025, 1, 31), (2026, 12, 15)]
)
def test_monthly_calendar_covers_one_year_without_gaps(year: int, month: int, day: int) -> None:
    periods = monthly_periods(year, month, day)
    assert len(periods) == 12
    assert [p.sequence for p in periods] == list(range(1, 13))
    assert periods[0].start_date == dt.date(year, month, day)
    for left, right in pairwise(periods):
        assert left.end_date + dt.timedelta(days=1) == right.start_date
        assert left.start_date <= left.end_date
    assert 365 <= (periods[-1].end_date - periods[0].start_date).days + 1 <= 366


def test_short_months_do_not_drift_from_calendar_anchor() -> None:
    periods = monthly_periods(2025, 1, 31)
    assert periods[1].start_date == dt.date(2025, 2, 28)
    assert periods[2].start_date == dt.date(2025, 3, 31)


@pytest.mark.parametrize(
    "year,month,day", [(1899, 1, 1), (9998, 1, 1), (2026, 2, 30), (2026, 13, 1)]
)
def test_invalid_calendar_is_rejected(year: int, month: int, day: int) -> None:
    with pytest.raises(ValidationFailedError):
        monthly_periods(year, month, day)


def test_period_transitions_enforce_terminal_lock_and_sequential_close() -> None:
    assert transition_permission("FUTURE", "OPEN", ()) == "period.manage"
    assert transition_permission("OPEN", "SOFT_CLOSED", ("SOFT_CLOSED",)) == "period.close"
    assert transition_permission("SOFT_CLOSED", "CLOSED", ("LOCKED", "CLOSED")) == "period.close"
    assert transition_permission("CLOSED", "OPEN", ()) == "period.reopen"
    assert transition_permission("SOFT_CLOSED", "OPEN", ()) == "period.reopen"
    assert transition_permission("CLOSED", "LOCKED", ("CLOSED",)) == "period.lock"
    for before, after, previous in [
        ("LOCKED", "OPEN", ()),
        ("OPEN", "CLOSED", ()),
        ("OPEN", "OPEN", ()),
        ("OPEN", "SOFT_CLOSED", ("OPEN",)),
        ("SOFT_CLOSED", "CLOSED", ("SOFT_CLOSED",)),
        ("CLOSED", "LOCKED", ("FUTURE",)),
    ]:
        with pytest.raises(ConflictError):
            transition_permission(before, after, previous)
