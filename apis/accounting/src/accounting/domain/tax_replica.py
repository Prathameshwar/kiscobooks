"""Pure ordering and immutability rules for the Catalog tax replica (no database).

Catalog's company policy generation orders every publication. A replica row moves only to a
strictly newer generation; an equal or older one is a redelivery or a late message and is
ignored. Between generations only a fixed set of fields may change: anything else means the
publisher rewrote history, which the consumer refuses rather than silently mirrors.
"""

import datetime as dt
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any, Literal

#: Fields a newer generation may change on an existing replica row.
MUTABLE_FIELDS: Mapping[str, frozenset[str]] = {
    "classification": frozenset({"valid_to", "description"}),
    "rule": frozenset({"name", "is_active"}),
    "rate": frozenset({"valid_to"}),
}

Decision = Literal["insert", "update", "ignore"]

WITHDRAW = "WITHDRAW"


def next_action(current: str | None, incoming: str) -> str:
    """The action a replica row records; a withdrawn row stays withdrawn."""
    return WITHDRAW if current == WITHDRAW else incoming


def effective_on(action: str, valid_from: dt.date, valid_to: dt.date | None, on: dt.date) -> bool:
    """Whether a dated replica row applies on ``on``.

    Catalog withdraws only rows that have not started and publishes them with ``valid_to ==
    valid_from``; read as a range that would be a one-day window, so a WITHDRAW row is never
    effective on any date.
    """
    if action == WITHDRAW:
        return False
    return valid_from <= on and (valid_to is None or on <= valid_to)


def decide(current_version: int | None, incoming_version: int) -> Decision:
    """Insert unknown rows, apply strictly newer generations and ignore everything else."""
    if current_version is None:
        return "insert"
    return "update" if incoming_version > current_version else "ignore"


def immutable_changes(
    current: Mapping[str, Any], incoming: Mapping[str, Any], mutable: Iterable[str]
) -> frozenset[str]:
    """Fields outside ``mutable`` whose incoming value differs from the stored one."""
    allowed = frozenset(mutable)
    return frozenset(
        key for key, value in incoming.items() if key not in allowed and current.get(key) != value
    )


def same_components(
    current: Iterable[Mapping[str, Any]], incoming: Iterable[Mapping[str, Any]]
) -> bool:
    """A published rate's components never change; compare them as an unordered set."""

    def key(rows: Iterable[Mapping[str, Any]]) -> list[tuple[tuple[str, str], ...]]:
        return sorted(
            tuple(sorted((name, repr(normal(value))) for name, value in row.items()))
            for row in rows
        )

    return key(current) == key(incoming)


def normal(value: Any) -> Any:
    """Compare decimals by value, so ``5`` and ``5.0000`` from the database agree."""
    return value.normalize() if isinstance(value, Decimal) else value
