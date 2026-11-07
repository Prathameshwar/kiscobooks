"""Replica lag is distinguishable from genuinely stale or retired entry references."""

import pytest
from billing_platform.errors import ConflictError
from sqlalchemy import select
from test_unit_admission import payload

from vouchers.models.core import VoucherMasterEvidence
from vouchers.tasks.documents import validate_masters

pytest_plugins = ("test_unit_admission",)


@pytest.mark.parametrize("source,requested,retired,message", [
    (None, 1, False, "still syncing"),
    (1, 2, False, "still syncing"),
    (2, 1, False, "unavailable or stale"),
    (1, 1, True, "unavailable or stale"),
])
async def test_master_lag_and_stale_entries_have_distinct_refusals(
    admission, source, requested, retired, message
):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        row = await db.scalar(select(VoucherMasterEvidence).where(
            VoucherMasterEvidence.entity_type == "item"
        ))
        if source is None:
            await db.delete(row)
        else:
            row.source_version = source
            if retired:
                row.status = "RETIRED"
        await db.flush()
        with pytest.raises(ConflictError, match=message):
            await validate_masters(db, current, payload(item, unit, item_version=requested),
                                  capture=False, kind="PURCHASE")
