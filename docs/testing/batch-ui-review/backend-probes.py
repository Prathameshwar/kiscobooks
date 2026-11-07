"""Check native rejection of values that the UI review probes accept."""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from catalog.schemas.simple_product_creation import SimpleBatchInput, SimpleCreationInput
from catalog.tasks import simple_batch_preparation


def test_backend_rejects_casefold_equivalent_codes():
    with pytest.raises(ValidationError, match="distinct"):
        SimpleCreationInput(name="Tea", base_unit_id=uuid7(), batch_enabled=True,
            batches=[{"code": "ss"}, {"code": "ß"}])


def test_backend_rejects_normalized_code_overflow():
    with pytest.raises(ValidationError, match="normalized"):
        SimpleBatchInput(code="\ufb03" * 40)


def test_backend_rejects_expiry_before_1000():
    with pytest.raises(ValidationError, match="1000"):
        SimpleBatchInput(code="LOT", expires_on="0001-01-01")


@pytest.mark.parametrize(("manufactured", "expires", "message"), [
    ("2026-01-01", "2026-02-01", "Expired opening"),
    ("2027-01-01", "2028-01-01", "cannot precede manufacture"),
])
async def test_native_preparation_rejects_invalid_opening_dates(monkeypatch, manufactured, expires, message):
    monkeypatch.setattr(simple_batch_preparation, "available", AsyncMock(return_value={
        "available": True, "required": False, "expiry_enabled": True,
        "expiry_required": False, "manufacture_date_required": False,
    }))
    monkeypatch.setattr(simple_batch_preparation, "effective", AsyncMock(return_value=None))
    access = SimpleNamespace(reference=AsyncMock(return_value=SimpleNamespace(shelf_life_days=None)))
    defaults = SimpleNamespace(
        configuration=SimpleNamespace(profiles=SimpleNamespace(inventory_template_revision_id=uuid7())),
        product_type_revision_id=uuid7(), quantity=SimpleNamespace(quantity_decimal_places=0, quantity_increment=1),
        price=SimpleNamespace(price_decimal_places=2, price_increment=None),
    )
    body = SimpleCreationInput(name="Tea", base_unit_id=uuid7(), batch_enabled=True,
        batches=[{"code": "LOT", "opening_quantity": "1", "purchase_price": "10",
                  "manufactured_on": manufactured, "expires_on": expires}])
    with pytest.raises(ValidationFailedError, match=message):
        await simple_batch_preparation.prepare_batches(
            access, defaults, body, dt.date(2026, 11, 7), dt.date(2026, 11, 7))
