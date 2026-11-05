"""Framework-independent strict scalar query validation."""

from collections import Counter
from collections.abc import Iterable

from billing_platform.errors import ValidationFailedError


def validate_query_names(names: Iterable[str], allowed: set[str]) -> None:
    counts = Counter(names)
    invalid = set(counts) - allowed
    invalid.update(key for key, count in counts.items() if count > 1)
    if invalid:
        raise ValidationFailedError("invalid query parameters", fields={
            key: "unknown or repeated parameter" for key in sorted(invalid)
        })
