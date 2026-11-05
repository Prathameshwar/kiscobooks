"""Configured tracking and date requirements fail before product admission."""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks import simple_batch_preparation


@pytest.mark.parametrize(
    ("selection", "required", "expiry_enabled", "expiry_required", "dates", "message"),
    [
        (None, False, True, False, {}, "Choose whether"),
        (False, True, True, False, {}, "not allowed"),
        (True, False, True, True, {}, "Enter expiry"),
        (True, False, False, False, {"expires_on": "2090-01-01"}, "Expiry is disabled"),
    ],
)
async def test_configured_batch_requirements(
    monkeypatch, selection, required, expiry_enabled, expiry_required, dates, message
):
    monkeypatch.setattr(
        simple_batch_preparation,
        "available",
        AsyncMock(
            return_value={
                "available": True,
                "required": required,
                "expiry_enabled": expiry_enabled,
                "expiry_required": expiry_required,
                "manufacture_date_required": False,
            }
        ),
    )
    monkeypatch.setattr(simple_batch_preparation, "effective", AsyncMock(return_value=None))
    access = SimpleNamespace(reference=AsyncMock(return_value=SimpleNamespace()))
    defaults = SimpleNamespace(
        configuration=SimpleNamespace(
            profiles=SimpleNamespace(inventory_template_revision_id=uuid7()),
        ),
        product_type_revision_id=uuid7(),
        quantity=object(),
        price=object(),
    )
    body = SimpleCreationInput(
        name="Goods",
        base_unit_id=uuid7(),
        batch_enabled=selection,
        batches=[{"code": "LOT1", **dates}] if selection else [],
    )
    with pytest.raises(ValidationFailedError, match=message):
        await simple_batch_preparation.prepare_batches(
            access, defaults, body, dt.date.today(), dt.date.today()
        )
