from decimal import Context, Decimal, localcontext

import pytest

from billing_platform.exact import exact_rate
from billing_platform.money import MoneyError


@pytest.mark.parametrize("value", ["83.12345678", "99999999999.99999999", "-99999999999.99999999", "0", 1])
def test_rate_storage_is_exact_and_context_independent(value):
    with localcontext(Context(prec=6)):
        result = exact_rate(value)
    assert result == Decimal(value)
    assert result.as_tuple().exponent == -8


@pytest.mark.parametrize("value", ["100000000000", "0.000000001", "NaN", "Infinity", 1.1, True, "bad", "1" * 129])
def test_unrepresentable_or_lossy_rate_is_refused(value):
    with pytest.raises(MoneyError):
        exact_rate(value)
