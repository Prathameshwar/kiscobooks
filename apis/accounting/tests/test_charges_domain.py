import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.money import RoundingMode

from accounting.domain.charges import ChargeTerms, Movement, total_charge

START = dt.date(2026, 4, 3)
TERMS = ChargeTerms(
    "INTEREST", Decimal("36.5"), "ANNUAL", "SIMPLE", "OUTSTANDING", 365, Decimal(0), None
)


def calc(days: int, movements: tuple[Movement, ...] = (), **changes: Any) -> Decimal:
    return total_charge(
        Decimal(100),
        START,
        START + dt.timedelta(days=days),
        movements,
        replace(TERMS, **changes),
        precision=2,
        rounding=RoundingMode.HALF_UP,
    )


def test_interest_partial_payment_and_unallocation_timeline() -> None:
    assert calc(30) == Decimal(3)
    movements = (
        Movement(START + dt.timedelta(days=10), Decimal(40)),
        Movement(START + dt.timedelta(days=20), Decimal(-40)),
    )
    assert calc(30, movements) == Decimal("2.60")
    assert calc(30, movements, basis="ORIGINAL") == 3
    assert calc(30, (Movement(START, Decimal(100)),)) == 0
    assert type(calc(30)) is Decimal


def test_fixed_minimum_cap_and_rate_bases() -> None:
    assert calc(30, method="FIXED", rate=Decimal(10)) == 10
    assert calc(30, minimum=Decimal(5)) == 5
    assert calc(30, cap=Decimal(2)) == 2
    assert calc(0) == 0
    assert calc(30, rate=Decimal(1), rate_period="MONTHLY") == 1
    assert calc(30, rate=Decimal(1), rate_period="DAILY") == 30
    assert calc(30, rate=Decimal(12), day_basis=360) == 1


def test_daily_compound_is_cumulative_and_interval_independent() -> None:
    assert calc(2, rate=Decimal(1), rate_period="DAILY", compound="DAILY") == Decimal("2.01")
    first = calc(10, compound="DAILY")
    cumulative = calc(30, compound="DAILY")
    assert first + (cumulative - first) == cumulative
    moves = (Movement(START + dt.timedelta(days=1), Decimal(50)),)
    assert calc(2, moves, rate=Decimal(1), rate_period="DAILY", compound="DAILY") == Decimal("1.51")


@pytest.mark.parametrize(
    "changes",
    [
        {"method": "X"},
        {"rate_period": "X"},
        {"compound": "X"},
        {"basis": "X"},
        {"day_basis": 366},
        {"minimum": Decimal(-1)},
        {"cap": Decimal(-1)},
    ],
)
def test_invalid_terms(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        calc(30, **changes)


@pytest.mark.parametrize("days", [-1, 3651])
def test_bounded_accrual_window(days: int) -> None:
    with pytest.raises(ValidationFailedError):
        calc(days)


def test_invalid_principal_history_and_overflow() -> None:
    with pytest.raises(ValidationFailedError):
        calc(30, (Movement(START, Decimal(101)),))
    with pytest.raises(ValidationFailedError):
        calc(30, (Movement(START, Decimal("NaN")),))
    with pytest.raises(ValidationFailedError):
        calc(3650, rate=Decimal(100), rate_period="DAILY", compound="DAILY")
