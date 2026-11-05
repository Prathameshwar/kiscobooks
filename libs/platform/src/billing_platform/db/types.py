"""Column type decorators.

Three jobs, each guarding a silent-corruption path:

* ``Uuid7`` stores a UUID as ``BINARY(16)`` — 16 bytes, time-ordered, clustering
  well as an InnoDB PK, instead of a 36-char string.
* ``Money`` / ``Quantity`` pin ``DECIMAL(19,4)`` and guarantee a ``Decimal``
  comes back. The MariaDB drivers can hand back ``float`` for a DECIMAL, and it
  is silent.
* ``UtcDateTime`` pins ``DATETIME(6)`` and rejects a naive datetime, so "UTC
  everywhere" is enforced at the column rather than by convention.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import BINARY, DateTime, Dialect, Numeric
from sqlalchemy.types import TypeDecorator

from billing_platform.constants import MONEY_PRECISION, MONEY_SCALE


class Uuid7(TypeDecorator[uuid.UUID]):
    """A UUID stored as ``BINARY(16)``."""

    impl = BINARY(16)
    cache_ok = True

    # `value: Any` rather than `uuid.UUID | None`: the runtime checks below are
    # the point of this decorator, and a narrower annotation makes them
    # statically unreachable while the wrong type still arrives at runtime — a
    # raw string id from a hand-written query, for one.
    def process_bind_param(self, value: Any, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, bytes):  # pragma: no cover - tolerated, not encouraged
            return value
        if not isinstance(value, uuid.UUID):
            raise TypeError(f"expected uuid.UUID, got {type(value).__name__}")
        return value.bytes

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return uuid.UUID(bytes=bytes(value))


class _FixedDecimal(TypeDecorator[Decimal]):
    """``DECIMAL(19,4)`` that always returns ``Decimal``."""

    impl = Numeric(precision=MONEY_PRECISION, scale=MONEY_SCALE, asdecimal=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("float is never stored in a money or quantity column; use Decimal")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int | str):
            return Decimal(value)
        raise TypeError(f"expected Decimal, int or str, got {type(value).__name__}")

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        # A driver handed back something else (asyncmy can return float for
        # DECIMAL). Coerce via str so no binary-float rounding is inherited.
        return Decimal(str(value))


class Money(_FixedDecimal):
    """A monetary amount. Always paired with a sibling currency column."""

    # SQLAlchemy checks the concrete decorator class, not inherited cache_ok.
    cache_ok = True


class Quantity(_FixedDecimal):
    """A quantity. Same fixed 4-place storage scale as money."""

    cache_ok = True


class UtcDateTime(TypeDecorator[dt.datetime]):
    """``DATETIME(6)`` holding UTC. Rejects naive datetimes on the way in."""

    impl = DateTime(timezone=False)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "mysql":
            from sqlalchemy.dialects.mysql import DATETIME

            return dialect.type_descriptor(DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime(timezone=False))

    def process_bind_param(self, value: dt.datetime | None, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise TypeError("naive datetime rejected; timestamps are UTC and must be tz-aware")
        return value.astimezone(dt.UTC).replace(tzinfo=None)

    def process_result_value(
        self, value: dt.datetime | None, dialect: Dialect
    ) -> dt.datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=dt.UTC)


def utcnow() -> dt.datetime:
    """Timezone-aware current UTC time. The only clock the platform reads."""
    return dt.datetime.now(dt.UTC)
