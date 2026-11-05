from __future__ import annotations

from decimal import Decimal

import pytest

from billing_platform.money import (
    MoneyError,
    RoundingMode,
    is_zero,
    quantize_storage,
    round_for_display,
    to_decimal,
)


def test_float_is_rejected_rather_than_converted() -> None:
    """By the time a float arrives the loss has already happened."""
    with pytest.raises(MoneyError):
        to_decimal(0.1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.5", "1234.5000"),
        ("1234.56789", "1234.5679"),
        (0, "0.0000"),
        ("-99.999949", "-99.9999"),
    ],
)
def test_storage_scale_is_always_four_places(raw: str | int, expected: str) -> None:
    assert quantize_storage(raw) == Decimal(expected)
    assert quantize_storage(raw).as_tuple().exponent == -4


def test_value_beyond_decimal_19_4_is_rejected() -> None:
    with pytest.raises(MoneyError, match="out of DECIMAL"):
        quantize_storage("99999999999999999999")


@pytest.mark.parametrize(
    ("raw", "precision", "mode", "expected"),
    [
        ("1234.5000", 2, RoundingMode.HALF_UP, "1234.50"),
        ("2.005", 2, RoundingMode.HALF_UP, "2.01"),
        ("2.005", 2, RoundingMode.HALF_EVEN, "2.00"),
        ("2.999", 0, RoundingMode.DOWN, "2"),
        ("1234.5678", 4, RoundingMode.HALF_UP, "1234.5678"),
    ],
)
def test_display_rounding_honours_the_company_mode(
    raw: str, precision: int, mode: RoundingMode, expected: str
) -> None:
    assert round_for_display(raw, precision, mode) == Decimal(expected)


def test_display_precision_beyond_storage_scale_is_rejected() -> None:
    with pytest.raises(MoneyError, match="precision must be"):
        round_for_display("1.0", 5)


def test_a_non_numeric_string_is_a_money_error_not_an_invalid_operation() -> None:
    """So a bad payload surfaces as 422 rather than a 500 from the decimal module."""
    with pytest.raises(MoneyError, match="not a decimal value"):
        to_decimal("twelve")


def test_a_decimal_passes_through_unchanged() -> None:
    value = Decimal("1.2345")
    assert to_decimal(value) is value


@pytest.mark.parametrize("raw", ["0", "0.0000", "-0.0000", "0E-8"])
def test_zero_is_recognised_at_any_scale(raw: str) -> None:
    """A stored zero is ``0.0000`` and a computed one may be ``-0.0000`` or
    ``0E-8``. All three must read as zero, which string comparison does not do."""
    assert is_zero(Decimal(raw)) is True
    assert str(Decimal(raw)) != "0" or raw == "0"


def test_a_small_non_zero_is_not_zero() -> None:
    assert is_zero(Decimal("0.0001")) is False


def test_rounding_mode_maps_to_a_decimal_constant() -> None:
    assert RoundingMode.HALF_UP.decimal_rounding == "ROUND_HALF_UP"
    assert RoundingMode.HALF_EVEN.decimal_rounding == "ROUND_HALF_EVEN"
    assert RoundingMode.DOWN.decimal_rounding == "ROUND_DOWN"


def test_rounding_mode_values_match_the_company_column() -> None:
    """``company.rounding_mode`` is a VARCHAR holding exactly these."""
    assert {m.value for m in RoundingMode} == {"half_up", "half_even", "down"}


def test_display_rounding_does_not_change_storage_value() -> None:
    """Display precision is presentation. It never rewrites what is stored."""
    stored = quantize_storage("1234.5678")
    shown = round_for_display(stored, 2)
    assert stored == Decimal("1234.5678")
    assert shown == Decimal("1234.57")
