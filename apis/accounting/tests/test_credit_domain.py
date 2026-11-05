from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.credit import decide


@pytest.mark.parametrize(
    "enforcement,status", [("BLOCK", "BLOCK"), ("WARN", "WARN"), ("OVERRIDE", "OVERRIDE_REQUIRED")]
)
def test_limit_and_overdue_decisions(enforcement: str, status: str) -> None:
    result = decide(
        Decimal(80), Decimal(15), Decimal(10), Decimal(100), Decimal(1), Decimal(0), enforcement
    )
    assert result.status == status and result.projected == 105
    assert result.reasons == ("LIMIT_EXCEEDED", "OVERDUE")
    assert type(result.projected) is Decimal


def test_exact_limit_tolerance_and_disabled_feature() -> None:
    assert (
        decide(
            Decimal(80), Decimal(10), Decimal(10), Decimal(100), Decimal(5), Decimal(5), "BLOCK"
        ).status
        == "ALLOW"
    )
    assert (
        decide(
            Decimal(100),
            Decimal(10),
            Decimal(10),
            Decimal(0),
            Decimal(5),
            Decimal(0),
            "BLOCK",
            enabled=False,
        ).status
        == "ALLOW"
    )
    assert (
        decide(Decimal(100), Decimal(10), Decimal(10), None, Decimal(0), Decimal(0), "BLOCK").status
        == "ALLOW"
    )


@pytest.mark.parametrize(
    "value", [Decimal(-1), Decimal("NaN"), Decimal("Infinity"), Decimal("1000000000000000")]
)
def test_invalid_money(value: Decimal) -> None:
    with pytest.raises(ValidationFailedError):
        decide(value, Decimal(0), Decimal(1), None, Decimal(0), Decimal(0), "BLOCK")


def test_invalid_enforcement_and_overflow() -> None:
    with pytest.raises(ValidationFailedError):
        decide(Decimal(0), Decimal(0), Decimal(1), None, Decimal(0), Decimal(0), "IGNORE")
    with pytest.raises(ValidationFailedError):
        decide(
            Decimal("999999999999999"),
            Decimal(1),
            Decimal(1),
            None,
            Decimal(0),
            Decimal(0),
            "BLOCK",
        )
