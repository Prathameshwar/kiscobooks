"""Read-only review probes: assert observed gaps, not desired fixed behavior.

Run with Catalog's virtualenv from apis/catalog. No database is needed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import datetime as dt
import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from catalog.schemas.advanced_product_creation import AdvancedOpeningInput
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks import simple_batch_preparation
from catalog.tasks.product_stock_choice import available, profile_values


async def test_batch_choice_preserves_required_expiry_and_fefo():
    template = SimpleNamespace(
        identifier_profile_id=None, lot_tracking=True, serial_tracking=False,
        expiry_required=True, manufacture_date_required=True, shelf_life_days=30,
        minimum_remaining_life_days=5, issue_strategy="FEFO", valuation_method="FIFO",
        negative_stock_policy="BLOCK",
    )
    product_type = SimpleNamespace(tracking_modes=["NONE", "BATCH"], require_expiry=False)
    access = SimpleNamespace(
        reference=AsyncMock(side_effect=[template, product_type]),
        context=AsyncMock(return_value=SimpleNamespace(
            features={"inventory", "batch_tracking", "expiry_tracking"}
        )),
    )
    config = SimpleNamespace(profiles=SimpleNamespace(inventory_template_revision_id=uuid7()))
    options = await available(access, config, uuid7(), "GOODS")
    assert options["available"] and options["expiry_required"]
    assert options["required"] is True
    with pytest.raises(ValidationFailedError, match="mandatory"):
        profile_values(template, SimpleNamespace(batch_enabled=False))


async def test_disabling_purchase_references_preserves_batch_opening_cost(monkeypatch):
    monkeypatch.setattr(simple_batch_preparation, "available", AsyncMock(return_value={
        "available": True, "required": False, "expiry_enabled": True,
        "expiry_required": False, "manufacture_date_required": False,
    }))
    monkeypatch.setattr(simple_batch_preparation, "effective", AsyncMock(return_value=None))
    monkeypatch.setattr(simple_batch_preparation, "sale_amounts", AsyncMock(return_value=[]))
    config = SimpleNamespace(
        profiles=SimpleNamespace(inventory_template_revision_id=uuid7()),
        pricing=SimpleNamespace(purchase_reference_mode="DISABLED", mrp_mode="DISABLED"),
    )
    defaults = SimpleNamespace(
        configuration=config, product_type_revision_id=uuid7(),
        quantity=SimpleNamespace(quantity_decimal_places=0, quantity_increment=1),
        price=SimpleNamespace(price_decimal_places=2, price_increment=None),
    )
    body = SimpleCreationInput(name="Goods", base_unit_id=uuid7(), batch_enabled=True,
        batches=[{"code": "LOT1", "opening_quantity": "1", "opening_unit_cost": "10"}])
    access = SimpleNamespace(reference=AsyncMock(return_value=SimpleNamespace()))
    prepared = await simple_batch_preparation.prepare_batches(
        access, defaults, body, dt.date.today(), dt.date.today())
    assert prepared == [{"prices": []}]


def test_advanced_zero_cost_is_accepted_before_internal_simple_conversion_rejects_it():
    opening = AdvancedOpeningInput(decision="OPEN", opening_date=dt.date.today(),
        opening_quantity="1", purchase_price="0")
    with pytest.raises(ValidationError, match="purchase_price"):
        SimpleCreationInput.model_validate({
            "kind": "GOODS", "name": "Goods", "base_unit_id": uuid7(),
            "batch_enabled": False, "opening_date": opening.opening_date,
            "opening_quantity": opening.opening_quantity,
            "purchase_price": opening.purchase_price,
        })
