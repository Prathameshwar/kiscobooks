"""B24: a Purchase bill that brings its goods into stock (owner decision 2026-11-03)."""

import uuid

import pytest
from pydantic import ValidationError
from voucher_execution.invoice import InvoiceSupply, InvoiceTaxContext, SupplyCalculation
from voucher_execution.stock import STOCK_PROFILES, StockInput
from voucher_execution.stock_facts import StockItemFact


def stock(**line_changes):
    line = {
        "line_id": str(uuid.uuid4()),
        "item_id": str(uuid.uuid4()),
        "warehouse_id": str(uuid.uuid4()),
        "quantity": "10",
    } | line_changes
    return {
        "action": "PURCHASE_INVOICE",
        "stock_date": "2026-11-03",
        "currency": "INR",
        "reason": "Supplier bill for goods received",
        "lines": [line],
    }


def supply(**changes):
    key = str(uuid.uuid4())
    return {
        "line_key": key,
        "item_line_key": key,
        "account_id": str(uuid.uuid4()),
        "account_version": 1,
        "supply_kind": "GOODS",
        "description": "Milk powder",
        "amount": "1000",
    } | changes


def test_the_bill_is_the_purchase_profile_of_its_stock_action():
    assert STOCK_PROFILES["PURCHASE_INVOICE"] == ("PURCHASE", "STANDARD")
    accepted = StockInput.model_validate(stock())
    assert accepted.action == "PURCHASE_INVOICE"


def test_purchase_goods_keep_independent_warehouses_bins_batches_and_serials():
    body = stock()
    first = body["lines"][0]
    first.update(
        bin_id=str(uuid.uuid4()),
        lot_id=str(uuid.uuid4()),
        unit_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
        quantity="2",
    )
    second = {
        **first,
        "line_id": str(uuid.uuid4()),
        "warehouse_id": str(uuid.uuid4()),
        "bin_id": None,
        "lot_id": None,
        "unit_ids": [],
        "quantity": "5",
    }
    body["lines"].append(second)
    accepted = StockInput.model_validate(body)
    assert accepted.lines[0].warehouse_id != accepted.lines[1].warehouse_id
    assert accepted.lines[0].lot_id is not None
    assert len(accepted.lines[0].unit_ids) == 2
    second["unit_ids"] = [first["unit_ids"][0]]
    with pytest.raises(ValidationError, match="physical unit cannot occur on two source lines"):
        StockInput.model_validate(body)


def test_the_bill_never_carries_a_received_value_accounting_costs_it():
    with pytest.raises(ValidationError, match="landed cost"):
        StockInput.model_validate(stock(received_value="1000"))


def test_a_receipt_note_reference_is_not_accepted_until_linking_is_built():
    with pytest.raises(ValidationError, match="Receipt Note"):
        StockInput.model_validate(stock(source_movement_id=str(uuid.uuid4())))


def test_goods_tax_profile_and_input_credit_round_trip():
    context = InvoiceTaxContext.model_validate(
        {"profile": "INDIA_DOMESTIC_GOODS", "place_of_supply": "IN-UP"}
    )
    assert context.profile == "INDIA_DOMESTIC_GOODS"
    ineligible = InvoiceSupply.model_validate(
        supply(input_credit="INELIGIBLE", input_credit_reason="Used for staff welfare")
    )
    assert ineligible.model_dump(mode="json")["input_credit"] == "INELIGIBLE"
    with pytest.raises(ValidationError, match="reason"):
        InvoiceSupply.model_validate(supply(input_credit="INELIGIBLE"))
    with pytest.raises(ValidationError, match="reason"):
        InvoiceSupply.model_validate(supply(input_credit_reason="Not ineligible"))
    with pytest.raises(ValidationError, match="goods"):
        InvoiceSupply.model_validate(
            supply(
                supply_kind="SERVICE",
                item_line_key=None,
                input_credit="INELIGIBLE",
                input_credit_reason="x" * 5,
            )
        )


def test_new_optional_fields_leave_existing_wire_and_hashes_unchanged():
    plain = InvoiceSupply.model_validate(supply())
    assert "input_credit" not in plain.model_dump(mode="json")
    assert "input_credit_reason" not in plain.model_dump(mode="json")
    line = SupplyCalculation.model_validate(
        {
            "key": str(uuid.uuid4()),
            "entered": "1",
            "commercial": "1",
            "taxable": "1",
            "taxes": [],
            "price_rounding": "0",
            "payable": "1",
        }
    )
    assert "stock_cost" not in line.model_dump(mode="json")
    costed = line.model_copy(update={"stock_cost": line.payable})
    assert costed.model_dump(mode="json")["stock_cost"] == "1.0000"


def test_item_facts_may_carry_the_purchase_tax_classification():
    facts = {
        "item_id": str(uuid.uuid4()),
        "family_id": str(uuid.uuid4()),
        "item_version": 1,
        "family_version": 1,
        "status": "ACTIVE",
        "family_status": "ACTIVE",
        "base_unit_id": str(uuid.uuid4()),
        "quantity_increment": "1",
        "quantity_decimal_places": 0,
        "profile_id": str(uuid.uuid4()),
        "profile_revision_id": str(uuid.uuid4()),
        "lot_tracking": False,
        "serial_tracking": False,
        "expiry_required": False,
        "manufacture_date_required": False,
        "shelf_life_days": None,
        "minimum_remaining_life_days": None,
        "issue_strategy": "FIFO",
        "valuation_method": "FIFO",
        "negative_stock_policy": "BLOCK",
        "sellable": True,
        "purchasable": True,
        "allowed_warehouse_ids": None,
        "warehouse_permissions": [],
    }
    without = StockItemFact.model_validate(facts)
    assert "purchase_tax" not in without.model_dump(mode="json")
    taxed = StockItemFact.model_validate(
        facts
        | {
            "purchase_tax": {
                "classification_id": str(uuid.uuid4()),
                "classification_version": 1,
                "code": "0402",
                "rule_id": str(uuid.uuid4()),
                "rule_version": 2,
                "treatment": "TAXABLE",
            }
        }
    )
    assert taxed.purchase_tax is not None and taxed.purchase_tax.code == "0402"
    with pytest.raises(ValidationError):
        StockItemFact.model_validate(
            facts
            | {
                "purchase_tax": {
                    "classification_id": str(uuid.uuid4()),
                    "classification_version": 1,
                    "code": "04X2",
                    "rule_id": str(uuid.uuid4()),
                    "rule_version": 2,
                    "treatment": "TAXABLE",
                }
            }
        )


def test_a_fence_request_asks_for_purchase_tax_only_when_needed():
    from voucher_execution.stock_facts import StockFenceRequest

    base = {
        "tenant_id": str(uuid.uuid4()),
        "company_id": str(uuid.uuid4()),
        "execution_id": str(uuid.uuid4()),
        "actor_user_id": str(uuid.uuid4()),
        "authority": {
            "actor_context": "a",
            "actor_signature": "0" * 64,
            "company_context": "c",
            "company_signature": "0" * 64,
        },
        "authority_expires_at": "2026-11-03T10:00:00+00:00",
        "stock_date": "2026-11-03",
        "content_hash": "a" * 64,
        "item_ids": [str(uuid.uuid4())],
        "warehouse_ids": [str(uuid.uuid4())],
    }
    plain = StockFenceRequest.model_validate(base)
    assert "include_purchase_tax" not in plain.model_dump(mode="json")
    asked = StockFenceRequest.model_validate(base | {"include_purchase_tax": True})
    assert asked.model_dump(mode="json")["include_purchase_tax"] is True
