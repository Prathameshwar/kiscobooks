"""Native dispatch/correction evidence stays distinct from recognized sales."""

import pytest
from inventory_fixture import inventory_records, parameters
from reporting_contract.inventory import Movement

from reports.domain.reporting.inventory import calculate
from reports.tasks.report_catalog import catalog


@pytest.mark.parametrize("action", ["DISPATCH", "REVERSAL"])
def test_native_actions_preserve_exact_turnover_without_claiming_a_sale(action):
    records, ids = inventory_records()
    movement = next(
        row["payload"]
        for row in records
        if row["payload"]["kind"] == "MOVEMENT" and row["payload"]["action"] == "SALE"
    )
    movement["action"] = action
    Movement.model_validate(movement)
    entry = catalog().resolve("STOCK_MOVEMENT")
    query = entry.handler.normalize(parameters("STOCK_MOVEMENT", ids))
    rows, _ = calculate("STOCK_MOVEMENT", records, query)
    own = next(row for row in rows if row["item_id"] == ids["item"] and row["owner"] == "OWN")
    assert own["outward"] == "40.0000" and own["sales"] == "0.0000"


def test_incremental_handoff_cannot_claim_complete_inventory_reports():
    records, ids = inventory_records()
    movements = [row for row in records if row["payload"]["kind"] == "MOVEMENT"]
    query = catalog().resolve("ITEM_LEDGER").handler.normalize(parameters("ITEM_LEDGER", ids))
    with pytest.raises(ValueError, match="complete inventory source coverage is unavailable"):
        calculate("ITEM_LEDGER", movements, query)
