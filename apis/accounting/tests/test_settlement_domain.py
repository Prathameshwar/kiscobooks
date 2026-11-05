from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.settlement import carrying_amount


def test_last_allocation_takes_the_exact_residual() -> None:
    first = carrying_amount(Decimal(3), Decimal(100), Decimal(3), Decimal(100), Decimal(1))
    second = carrying_amount(Decimal(3), Decimal(100), Decimal(2), Decimal(100) - first, Decimal(1))
    last = carrying_amount(
        Decimal(3), Decimal(100), Decimal(1), Decimal(100) - first - second, Decimal(1)
    )
    assert first == second == Decimal("33.3333") and last == Decimal("33.3334")
    assert type(last) is Decimal


@pytest.mark.parametrize(
    "remaining,base_remaining,allocated",
    [
        ("1", "10", "2"),
        ("0", "0", "1"),
        ("2", "-1", "1"),
        ("4", "10", "1"),
        ("2", "101", "1"),
        ("2", "10", "0"),
    ],
)
def test_invalid_or_excess_allocation(remaining: str, base_remaining: str, allocated: str) -> None:
    with pytest.raises(ValidationFailedError):
        carrying_amount(
            Decimal(3),
            Decimal(100),
            Decimal(remaining),
            Decimal(base_remaining),
            Decimal(allocated),
        )
