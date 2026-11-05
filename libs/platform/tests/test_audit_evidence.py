import datetime as dt
import uuid
from decimal import Decimal

import pytest

from billing_platform.audit_evidence import scalar


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (True, "true"),
        (False, "false"),
        (dt.date(2026, 9, 17), "2026-09-17"),
        (Decimal("900719925474099.1234"), "900719925474099.1234"),
        (uuid.UUID(int=1), "00000000-0000-0000-0000-000000000001"),
        (10, "10"),
        ("INR", "INR"),
    ],
)
def test_scalar_preserves_exact_typed_values(value, expected):
    assert scalar(value) == expected


@pytest.mark.parametrize("value", [1.23, [], {}, b"untrusted"])
def test_scalar_rejects_float_and_arbitrary_data(value):
    with pytest.raises(ValueError, match="unsupported audit scalar"):
        scalar(value)
