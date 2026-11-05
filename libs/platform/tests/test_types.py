"""Type round-trip tests.

The Decimal test is the one worth having before any table exists: a driver
handing back ``float`` for a ``DECIMAL`` is silent, and it is far easier to catch
on one column now than to find in ``billing`` later.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import TypeDecorator

from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.db.types import Money, Quantity, UtcDateTime, Uuid7, utcnow
from billing_platform.ids import uuid7
from tests.helpers import MYSQL, bind, result
from tests.models import TenantThing


async def test_money_round_trips_as_decimal_not_float(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with unfiltered():
        session.add(
            TenantThing(
                id=uuid7(),
                tenant_id=tenant_a,
                name="invoice",
                amount=Decimal("1234.5678"),
                currency="INR",
                qty=Decimal("2.5000"),
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(TenantThing))).scalar_one()

    assert isinstance(row.amount, Decimal)
    assert isinstance(row.qty, Decimal)
    assert type(row.amount) is Decimal, "the driver handed back a non-Decimal"
    assert row.amount == Decimal("1234.5678")


async def test_quantity_keeps_four_decimal_places(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A broken pharma pack or a 0.3333-hour time entry needs all four."""
    with unfiltered():
        session.add(
            TenantThing(id=uuid7(), tenant_id=tenant_a, name="strip", qty=Decimal("0.3333"))
        )
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(TenantThing))).scalar_one()

    assert row.qty == Decimal("0.3333")


async def test_float_bound_to_a_money_column_is_rejected(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with unfiltered():
        session.add(
            TenantThing(
                id=uuid7(),
                tenant_id=tenant_a,
                name="bad",
                amount=1234.56,
            )
        )
        with pytest.raises(Exception, match="float is never stored"):
            await session.commit()
        await session.rollback()


async def test_uuid_round_trips_through_binary_16(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    row_id = uuid7()
    with unfiltered():
        session.add(TenantThing(id=row_id, tenant_id=tenant_a, name="x"))
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(TenantThing))).scalar_one()

    assert isinstance(row.id, uuid.UUID)
    assert row.id == row_id
    assert row.tenant_id == tenant_a


async def test_timestamps_come_back_utc_aware(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with unfiltered():
        session.add(TenantThing(id=uuid7(), tenant_id=tenant_a, name="x"))
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(TenantThing))).scalar_one()

    assert row.created_at.tzinfo is not None
    assert row.created_at.utcoffset() == dt.timedelta(0)


def test_utcnow_is_timezone_aware() -> None:
    assert utcnow().tzinfo is dt.UTC


# --- bind and result processing, exercised directly ---------------------------
#
# The paths below are the ones a MariaDB driver reaches and SQLite does not, so
# they are driven through the type rather than through a query. The dialect-level
# behaviour they stand in for is retested against a real container under the
# ``mariadb`` marker.


def test_naive_datetime_is_rejected_on_bind() -> None:
    """ "UTC everywhere" enforced at the column, not by convention."""
    with pytest.raises(TypeError, match="naive datetime rejected"):
        bind(UtcDateTime(), dt.datetime(2026, 9, 3, 12, 0))


def test_a_non_utc_datetime_is_converted_not_rejected() -> None:
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    stored = bind(UtcDateTime(), dt.datetime(2026, 9, 3, 17, 30, tzinfo=ist))

    assert stored == dt.datetime(2026, 9, 3, 12, 0)
    assert stored.tzinfo is None


def test_timestamp_column_is_datetime_fsp_6_on_mariadb() -> None:
    """Second-granularity timestamps cannot order two writes in one request."""
    impl = UtcDateTime().load_dialect_impl(MYSQL)
    assert isinstance(impl, mysql.DATETIME)
    assert impl.fsp == 6


def test_a_float_from_the_driver_is_coerced_via_str() -> None:
    """asyncmy can hand back ``float`` for a DECIMAL. Coercing through ``str``
    is what stops binary-float error being inherited into the stored value."""
    assert result(Money(), 1234.5678, MYSQL) == Decimal("1234.5678")
    # What the naive `Decimal(value)` would have produced instead:
    assert Decimal(1234.5678) != Decimal("1234.5678")


def test_a_string_from_the_driver_becomes_a_decimal() -> None:
    assert result(Quantity(), "0.3333", MYSQL) == Decimal("0.3333")


@pytest.mark.parametrize("raw", [7, "7.5"])
def test_int_and_str_are_accepted_on_bind(raw: int | str) -> None:
    assert bind(Money(), raw) == Decimal(raw)


def test_an_unsupported_type_is_rejected_on_bind() -> None:
    with pytest.raises(TypeError, match="expected Decimal, int or str"):
        bind(Money(), [1])


def test_a_non_uuid_id_is_rejected_on_bind() -> None:
    """A raw string id from a hand-written query fails loudly, not silently."""
    with pytest.raises(TypeError, match="expected uuid.UUID"):
        bind(Uuid7(), str(uuid7()))


@pytest.mark.parametrize("column_type", [Uuid7(), Money(), Quantity(), UtcDateTime()])
def test_none_passes_through_both_directions(column_type: TypeDecorator[object]) -> None:
    assert bind(column_type, None) is None
    assert result(column_type, None) is None
