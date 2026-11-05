"""B44 cash evidence conserves one existing tender amount."""

from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from vouchers.domain.cash_denominations import Denomination, validate_cash_tender

FACES = frozenset({Decimal("500"), Decimal("100"), Decimal("50")})


def test_exact_denominations_equal_one_cash_tender():
    rows = (Denomination(Decimal(500), 1), Denomination(Decimal(100), 2))
    assert validate_cash_tender(Decimal(700), rows, allowed_faces=FACES) == Decimal("700.0000")


def test_mismatch_duplicate_unapproved_and_fractional_count_refused():
    with pytest.raises(ValidationFailedError, match="do not equal"):
        validate_cash_tender(Decimal(600), (Denomination(Decimal(500), 1),), allowed_faces=FACES)
    with pytest.raises(ValidationFailedError, match="distinct"):
        validate_cash_tender(
            Decimal(1000),
            (Denomination(Decimal(500), 1), Denomination(Decimal(500), 1)),
            allowed_faces=FACES,
        )
    with pytest.raises(ValidationFailedError, match="not allowed"):
        validate_cash_tender(Decimal(200), (Denomination(Decimal(200), 1),), allowed_faces=FACES)
    with pytest.raises(ValidationFailedError, match="count"):
        validate_cash_tender(Decimal(500), (Denomination(Decimal(500), True),), allowed_faces=FACES)
