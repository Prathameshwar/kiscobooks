"""Native key/constraint enforcement before stock posting is exposed."""

import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from accounting.models.stock import StockBalance, StockPosition
from tests.conftest import COMPANY, TENANT, USER

ZERO = uuid.UUID(int=0)


def position(tenant=TENANT, company=COMPANY, **changes):
    return StockPosition(
        id=uuid7(),
        tenant_id=tenant,
        company_id=company,
        created_by=USER,
        updated_by=USER,
        row_version=1,
        **(
            {
                "item_id": uuid7(),
                "warehouse_id": uuid7(),
                "bin_id": None,
                "bin_key": ZERO,
                "lot_id": None,
                "lot_key": ZERO,
                "owner_kind": "COMPANY",
                "custody_kind": "WAREHOUSE",
                "disposition": "USABLE",
            }
            | changes
        ),
    )


async def test_canonical_absent_bin_and_lot_cannot_duplicate_or_lie(app):
    factory = app.state.session_factory
    row = position()
    with tenant_scope(TENANT):
        async with factory.begin() as db:
            db.add(row)
        for changes in (
            {"item_id": row.item_id, "warehouse_id": row.warehouse_id},
            {"lot_key": uuid7()},
            {"bin_key": uuid7()},
            {"bin_id": uuid7(), "bin_key": uuid7()},
            {"disposition": "DAMAGED"},
        ):
            with pytest.raises((IntegrityError, OperationalError)) as rejected:
                async with factory.begin() as db:
                    db.add(position(**changes))
            if isinstance(rejected.value, OperationalError):
                assert rejected.value.orig.args[0] == 3819  # Native MySQL CHECK violation.
        async with factory() as db:
            stored = await db.get(StockPosition, row.id)
            assert stored and stored.lot_key == ZERO and stored.bin_key == ZERO
            stored.warehouse_id = uuid7()
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()


async def test_position_and_guarded_balance_have_tenant_isolation_and_nonnegative_storage(app):
    factory = app.state.session_factory
    other = uuid7()
    rows = []
    for tenant, company in ((TENANT, COMPANY), (other, uuid7())):
        row = position(tenant, company)
        rows.append(row)
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(row)
                await db.flush()
                db.add(
                    StockBalance(
                        id=uuid7(),
                        tenant_id=tenant,
                        company_id=company,
                        created_by=USER,
                        updated_by=USER,
                        row_version=1,
                        position_id=row.id,
                        quantity=Decimal("2"),
                    )
                )
    with tenant_scope(TENANT):
        async with factory() as db:
            assert [row.id for row in await db.scalars(select(StockPosition))] == [rows[0].id]
            balances = list(await db.scalars(select(StockBalance)))
            assert len(balances) == 1 and isinstance(balances[0].quantity, Decimal)
            balances[0].quantity = Decimal("-0.0001")
            with pytest.raises((IntegrityError, OperationalError)) as rejected:
                await db.flush()
            if isinstance(rejected.value, OperationalError):
                assert rejected.value.orig.args[0] == 3819
