"""Worked stock values and eligibility, independent of ORM/session/transport."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.money import RoundingMode

from accounting.domain.stock_costing import CostBucket, exact, fifo, linked_return, moving_average
from accounting.domain.stock_eligibility import issue_eligible, posting_day, quantity


def bucket(qty: str, value: str) -> CostBucket:
    return CostBucket(uuid.uuid4(), Decimal(qty), Decimal(value))


def test_fifo_and_average_are_warehouse_values_not_physical_batch_selection() -> None:
    first, second = bucket("3", "30"), bucket("2", "30")
    allocations = fifo([first, second], Decimal("4"))
    assert [(row.quantity, row.value) for row in allocations] == [
        (Decimal("3"), Decimal("30")),
        (Decimal("1"), Decimal("15")),
    ]
    average = moving_average(bucket("5", "60"), Decimal("4"))
    assert average.value == Decimal("48") and isinstance(average.value, Decimal)
    assert sum((row.value for row in allocations), Decimal("0")) == Decimal("45")
    with pytest.raises(ConflictError):
        fifo([first], Decimal("4"))
    with pytest.raises(ConflictError):
        fifo([first, first], Decimal("1"))


def test_partial_consumption_and_returns_conserve_the_last_currency_residual() -> None:
    original = bucket("3", "1.00")
    first = linked_return(original, Decimal("0"), Decimal("0"), Decimal("1"), places=2)
    second = linked_return(original, Decimal("1"), first.value, Decimal("1"), places=2)
    last = linked_return(original, Decimal("2"), first.value + second.value, Decimal("1"), places=2)
    assert [row.value for row in (first, second, last)] == [
        Decimal("0.33"),
        Decimal("0.34"),
        Decimal("0.33"),
    ]
    assert first.value + second.value + last.value == original.value
    with pytest.raises(ConflictError):
        linked_return(original, Decimal("3"), Decimal("1"), Decimal("1"))
    with pytest.raises(ConflictError):
        linked_return(original, Decimal("4"), Decimal("1"), Decimal("1"))
    with pytest.raises(ConflictError):
        linked_return(original, Decimal("1"), Decimal("2"), Decimal("1"))


def test_large_precise_and_explicit_zero_cost_remain_decimal() -> None:
    high = bucket("999999999999999.9999", "999999999999999.9999")
    assert moving_average(high, Decimal("999999999999999.9998")).value == Decimal(
        "999999999999999.9998"
    )
    assert moving_average(bucket("2", "0"), Decimal("1")).value == Decimal("0.0000")
    with pytest.raises(ConflictError):
        bucket("0", "0.0001")
    for invalid in (
        Decimal("-1"),
        Decimal("1.00001"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1000000000000000"),
        1.5,
        True,
    ):
        with pytest.raises(ValidationFailedError):
            exact(invalid)
    with pytest.raises(ValueError):
        moving_average(bucket("1", "1"), Decimal("1"), places=5)


def test_expiry_includes_the_date_and_company_timezone_controls_the_day() -> None:
    expiry = dt.date(2026, 10, 28)
    values = {
        "active": True,
        "held": False,
        "manufactured_on": dt.date(2026, 10, 1),
        "expires_on": expiry,
        "minimum_remaining_life_days": None,
    }
    issue_eligible(day=expiry, **values)
    for change in (
        {"held": True},
        {"active": False},
        {"minimum_remaining_life_days": 1},
        {"manufactured_on": dt.date(2026, 10, 29)},
    ):
        with pytest.raises(ConflictError):
            issue_eligible(day=expiry, **(values | change))
    with pytest.raises(ConflictError):
        issue_eligible(day=dt.date(2026, 10, 29), **values)
    with pytest.raises(ConflictError):
        issue_eligible(
            day=expiry, **(values | {"expires_on": None, "minimum_remaining_life_days": 1})
        )
    now = dt.datetime(2026, 10, 27, 20, tzinfo=dt.UTC)
    posting_day(expiry, now=now, timezone="Asia/Kolkata", last_posted_day=expiry)
    with pytest.raises(ValidationFailedError):
        posting_day(expiry, now=now, timezone="UTC", last_posted_day=None)
    with pytest.raises(ConflictError):
        posting_day(dt.date(2026, 10, 27), now=now, timezone="UTC", last_posted_day=expiry)
    with pytest.raises(ValueError):
        posting_day(expiry, now=now.replace(tzinfo=None), timezone="UTC", last_posted_day=None)


def test_native_quantity_grid_and_serial_indivisibility() -> None:
    quantity(Decimal("1.5"), increment=Decimal("0.25"))
    quantity(Decimal("2"), increment=Decimal("1"), serialized=True)
    for qty, step, serial in (("1.1", "0.25", False), ("1.5", "0.5", True), ("0", "1", False)):
        with pytest.raises(ValidationFailedError):
            quantity(Decimal(qty), increment=Decimal(step), serialized=serial)


def test_company_rounding_is_used_without_losing_the_final_residual() -> None:
    for mode, expected in (
        (RoundingMode.HALF_UP, "0.01"),
        (RoundingMode.HALF_EVEN, "0.00"),
        (RoundingMode.DOWN, "0.00"),
    ):
        source = bucket("2", "0.01")
        first = moving_average(source, Decimal("1"), places=2, rounding=mode)
        assert first.value == Decimal(expected)
        last = linked_return(
            source, first.quantity, first.value, Decimal("1"), places=2, rounding=mode
        )
        assert first.value + last.value == source.value
