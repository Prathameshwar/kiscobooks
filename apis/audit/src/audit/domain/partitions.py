"""Monthly RANGE-partition arithmetic (docs/audit.md §6). Pure and DB-free.

Partition ``pYYYYMM`` holds rows with ``occurred_at`` in that calendar month; its RANGE
upper bound is the first instant of the *next* month (``VALUES LESS THAN`` is exclusive).
``tasks/partitions`` turns these names and boundaries into ``ALTER TABLE`` statements.
"""

from __future__ import annotations

import datetime as dt

#: The always-present catch-all tail (see the create migration). Never dropped; the
#: create-ahead job reorganizes it into concrete months so inserts never fall into it.
MAX_PARTITION: str = "pmax"


def partition_name(year: int, month: int) -> str:
    return f"p{year:04d}{month:02d}"


def add_months(year: int, month: int, count: int) -> tuple[int, int]:
    """``(year, month)`` shifted by ``count`` months (``count`` may be negative)."""
    index = (year * 12 + (month - 1)) + count
    return index // 12, index % 12 + 1


def upper_bound(year: int, month: int) -> dt.date:
    """The exclusive RANGE bound for ``pYYYYMM`` — the first day of the next month."""
    next_year, next_month = add_months(year, month, 1)
    return dt.date(next_year, next_month, 1)


def upper_bound_literal(year: int, month: int) -> str:
    """The bound as the ``DATETIME`` literal the DDL uses."""
    return f"{upper_bound(year, month).isoformat()} 00:00:00"


def months_to_provision(today: dt.date, *, ahead: int) -> list[tuple[int, int]]:
    """The months whose partitions should exist now: the current month through ``ahead``.

    Returned oldest-first, so the caller reorganizes ``pmax`` in order.
    """
    return [add_months(today.year, today.month, offset) for offset in range(ahead + 1)]


def is_expired(year: int, month: int, *, today: dt.date, retention_days: int) -> bool:
    """Whether every row ``pYYYYMM`` could hold is older than the retention floor.

    True only when the partition's newest possible instant (its exclusive upper bound) is
    itself beyond ``retention_days`` before ``today`` — so a partition is never dropped
    while any row in it is still inside the window.
    """
    return upper_bound(year, month) <= today - dt.timedelta(days=retention_days)


def parse_partition_name(name: str) -> tuple[int, int] | None:
    """``pYYYYMM`` → ``(year, month)``; ``None`` for ``pmax`` or any non-monthly name."""
    if len(name) != 7 or not name.startswith("p") or not name[1:].isdigit():
        return None
    year, month = int(name[1:5]), int(name[5:7])
    if not 1 <= month <= 12:
        return None
    return year, month


def missing_months(
    existing: set[str], *, today: dt.date, ahead: int
) -> list[tuple[int, int]]:
    """The months that should be provisioned but are not, oldest-first.

    Pure input to the create-ahead job so the decision is unit-testable without a
    database: the job turns each into one ``REORGANIZE PARTITION pmax`` (§6).
    """
    return [
        (year, month)
        for year, month in months_to_provision(today, ahead=ahead)
        if partition_name(year, month) not in existing
    ]


def droppable(existing: set[str], *, today: dt.date, retention_days: int) -> list[str]:
    """The monthly partitions whose entire month has passed the retention floor.

    ``pmax`` and any non-monthly name are never returned — the tail is permanent and only
    ever reorganized, never dropped (§4.1). Returned oldest-first.
    """
    expired: list[tuple[int, int]] = []
    for name in existing:
        parsed = parse_partition_name(name)
        if parsed is None:
            continue
        year, month = parsed
        if is_expired(year, month, today=today, retention_days=retention_days):
            expired.append((year, month))
    return [partition_name(y, m) for y, m in sorted(expired)]
