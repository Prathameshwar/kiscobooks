import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.http_query import validate_query_names


def test_strict_scalar_query_rejects_unknown_and_duplicate_names() -> None:
    validate_query_names(["limit", "cursor"], {"limit", "cursor"})
    for values in (["tenant_id"], ["limit", "limit"]):
        with pytest.raises(ValidationFailedError):
            validate_query_names(values, {"limit", "cursor"})
