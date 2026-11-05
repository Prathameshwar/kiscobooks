"""Report review diagnostics over complete, disposable fixture evidence."""

from decimal import Decimal

from inventory_fixture import inventory_records, parameters
from reports.domain.reporting.inventory import calculate
from reports.schemas.inventory import MovementParameters


def test_dispatch_outward_has_no_action_breakdown_or_last_consumption():
    records, ids = inventory_records()
    for record in records:
        if (
            record["payload"]["kind"] == "MOVEMENT"
            and record["payload"]["action"] == "SALE"
        ):
            record["payload"]["action"] = "DISPATCH"
    params = MovementParameters.model_validate(
        parameters("STOCK_MOVEMENT", ids) | {"nonmoving_days": 20}
    ).model_dump(mode="json")
    rows, _ = calculate("STOCK_MOVEMENT", records, params)
    own = next(
        row for row in rows if row["item_id"] == ids["item"] and row["owner"] == "OWN"
    )
    assert Decimal(own["outward"]) == Decimal("40")
    assert all(
        Decimal(own[key]) == 0
        for key in ("sales", "consumption", "supplier_returns", "transfer_out")
    )
    assert "dispatch" not in own and "reversals" not in own
    assert own["last_consumption_date"] is None and own["nonmoving"] is True


def test_movement_only_native_feed_cannot_build_inventory_reports():
    import pytest

    records, ids = inventory_records()
    records = [record for record in records if record["payload"]["kind"] == "MOVEMENT"]
    with pytest.raises(ValueError, match="coverage is unavailable"):
        calculate("ITEM_LEDGER", records, parameters("ITEM_LEDGER", ids))
