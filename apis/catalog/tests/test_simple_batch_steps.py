"""Batch openings generate one native manifest and matching common voucher lines."""

from decimal import Decimal

from billing_platform.ids import uuid7
from voucher_execution.stock import StockInput

from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks.simple_creation_steps import next_command


async def test_batch_opening_lines_use_each_rows_cost_and_skip_zero_stock():
    company, item, identity, unit, revision, warehouse = (uuid7() for _ in range(6))
    lots = [str(uuid7()) for _ in range(3)]
    body = SimpleCreationInput(
        name="Tea",
        base_unit_id=unit,
        batch_enabled=True,
        batches=[
            {"code": "A", "opening_quantity": "3", "purchase_price": "12.50"},
            {"code": "B", "opening_quantity": "2", "purchase_price": "15.25"},
            {"code": "C", "purchase_price": "20"},
        ],
    )

    class Owners:
        async def call(self, service, method, path, data=None):
            if service == "catalog":
                return {
                    "units": [{"usage_role": "BASE", "revision_id": str(revision)}],
                    "item_version": 2,
                }
            capture = data["opening"]
            return {
                "base_quantity": capture["entered_quantity"],
                "received_value": str(
                    Decimal(capture["entered_quantity"]) * Decimal(capture["unit_cost"])
                ),
            }

    progress = {
        "batch_ids": lots,
        "currency": "INR",
        "opening_date": "2026-04-01",
        "warehouse_id": str(warehouse),
        "type_revision_id": str(uuid7()),
    }
    opening = await next_command(Owners(), company, identity, "OPENING", body, progress, item)
    assert len(opening["body"]["lines"]) == 2
    progress.update(manifest=opening["body"], control_id=str(uuid7()))
    voucher = await next_command(Owners(), company, identity, "VOUCHER", body, progress, item)
    stock = StockInput.model_validate(voucher["body"]["stock"])
    assert [str(line.lot_id) for line in stock.lines] == lots[:2]
    assert [line.received_value for line in stock.lines] == [Decimal("37.50"), Decimal("30.50")]
    assert len({line.opening.source_key for line in stock.lines}) == 2
    assert [line["line_key"] for line in voucher["body"]["lines"]] == [
        str(line.line_id) for line in stock.lines
    ]
