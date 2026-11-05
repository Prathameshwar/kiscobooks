import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from voucher_execution.stock import StockInput


def body(action="RECEIPT", **changes):
    return {
        "action": action,
        "stock_date": "2026-10-28",
        "currency": "INR",
        "reason": "Approved physical source evidence",
        "lines": [
            {
                "line_id": str(uuid.uuid4()),
                "item_id": str(uuid.uuid4()),
                "warehouse_id": str(uuid.uuid4()),
                "quantity": "2",
                "received_value": "12.34",
            }
        ],
        **changes,
    }


def test_typed_stock_receipt_retains_decimal_wire_values():
    accepted = StockInput.model_validate(body())
    assert isinstance(accepted.lines[0].quantity, Decimal)
    assert accepted.model_dump(mode="json")["lines"][0]["received_value"] == "12.3400"
    assert accepted.model_dump(mode="json")["lines"][0]["quantity"] == "2.0000"


def test_stock_retains_entered_fixed_and_actual_measured_quantities():
    raw = body()
    raw["lines"][0]["quantity_entry"] = {
        "entered_unit_id": str(uuid.uuid4()),
        "unit_revision_id": str(uuid.uuid4()),
        "entered_quantity": "1",
    }
    accepted = StockInput.model_validate(raw)
    assert accepted.lines[0].quantity_entry.entered_quantity == Decimal("1")
    raw["lines"][0]["quantity_entry"]["measured_base_quantity"] = "2"
    assert StockInput.model_validate(raw).lines[0].quantity_entry.measured_base_quantity == Decimal(
        "2"
    )


def test_additive_opening_fields_preserve_existing_receipt_wire_hash_shape():
    accepted = StockInput.model_validate(body())
    wire = accepted.model_dump(mode="json")
    assert "opening_control_id" not in wire
    assert "opening" not in wire["lines"][0]
    assert "quantity_entry" not in wire["lines"][0]
    assert StockInput.model_validate(wire).model_dump(mode="json") == wire


def test_compatible_wire_keeps_strongly_typed_output_schemas():
    schema = StockInput.model_json_schema(mode="serialization")
    assert schema["properties"]["lines"]["items"]["$ref"].endswith("/StockLine")
    line = schema["$defs"]["StockLine"]
    assert line["properties"]["quantity"]["type"] == "string"
    assert {"line_id", "item_id", "warehouse_id", "quantity"} <= set(line["required"])


@pytest.mark.parametrize("quantity", [1.1, True, "0", "-1", "1.00001", "NaN"])
def test_exact_positive_base_quantities(quantity):
    values = body()
    values["lines"][0]["quantity"] = quantity
    with pytest.raises(ValidationError):
        StockInput.model_validate(values)


def test_zero_cost_is_explicit_and_not_an_unavailable_value():
    values = body()
    values["lines"][0]["received_value"] = "0"
    with pytest.raises(ValidationError):
        StockInput.model_validate(values)
    values["lines"][0]["zero_value_reason"] = "Reviewed donated stock"
    assert StockInput.model_validate(values).lines[0].received_value == 0


def test_returns_transfers_openings_and_unit_reuse_have_closed_shapes():
    for action in (
        "DISPATCH",
        "TRANSFER",
        "TRANSFER_DISPATCH",
        "TRANSFER_RECEIPT",
        "CUSTOMER_RETURN",
        "SUPPLIER_RETURN",
        "OPENING",
    ):
        values = body(action)
        with pytest.raises(ValidationError):
            StockInput.model_validate(values)
        line = values["lines"][0]
        if action != "OPENING":
            line.pop("received_value")
        if action in {"TRANSFER", "TRANSFER_DISPATCH"}:
            line["destination_warehouse_id"] = str(uuid.uuid4())
        if action in {"CUSTOMER_RETURN", "SUPPLIER_RETURN", "TRANSFER_RECEIPT"}:
            line["source_movement_id"] = str(uuid.uuid4())
        if action == "OPENING":
            values["opening_mode"] = "COMBINED"
        assert StockInput.model_validate(values).action == action
    values = body("OPENING", opening_mode="LINKED_GL")
    with pytest.raises(ValidationError):
        StockInput.model_validate(values)
    values["lines"][0]["opening_journal_line_id"] = str(uuid.uuid4())
    assert StockInput.model_validate(values).opening_mode == "LINKED_GL"
    values = body()
    values["lines"][0]["unit_ids"] = [str(uuid.uuid4())] * 2
    with pytest.raises(ValidationError):
        StockInput.model_validate(values)
