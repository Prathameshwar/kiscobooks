"""Merchandising membership invariants, independent of storage and authorization."""

import datetime as dt
from collections.abc import Iterable

from billing_platform.errors import ConflictError


class CategoryCardinalityError(ConflictError):
    """A selection violates cardinality, distinct from an unavailable reference."""


def cardinality(mode: str, flags: Iterable[bool]) -> None:
    values = list(flags)
    if mode not in {"SINGLE", "MULTIPLE"}:
        raise ConflictError("unknown category scheme membership mode")
    if sum(values) > 1 or (mode == "SINGLE" and len(values) > 1):
        raise CategoryCardinalityError("category assignment exceeds scheme cardinality")


def boundaries(
    intervals: Iterable[tuple[dt.date, dt.date | None]], start: dt.date
) -> list[dt.date]:
    dates = {start}
    for first, last in intervals:
        if first >= start:
            dates.add(first)
        if last is not None and start <= last < dt.date.max:
            dates.add(last + dt.timedelta(days=1))
    return sorted(dates)
