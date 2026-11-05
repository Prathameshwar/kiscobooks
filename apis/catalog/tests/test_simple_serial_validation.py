"""Invalid serial input is rejected before any native product is created."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from catalog.schemas.simple_product_creation import SimpleCreationInput, SimpleSerialOptions
from catalog.tasks import simple_serial_preparation as serials
from catalog.tasks.simple_product_creation import creation_request


def identifier(value, kind="SERIAL", slot=1):
    return {"identifier_type": kind, "value": value, "slot": slot}


@pytest.mark.parametrize(
    ("rows", "quantity", "enabled", "kind", "message"),
    [
        ([[identifier("A")]], "2", True, "SERIAL", "must equal"),
        ([[identifier("ABC")], [identifier("ＡＢＣ")]], "2", True, "SERIAL", "another unit"),  # noqa: RUF001
        ([[identifier("A"), identifier("B")]], "1", True, "SERIAL", "duplicate identifier or slot"),
        ([[identifier("490154203237519", "IMEI")]], "1", True, "IMEI", "checksum"),
        ([[identifier("A", slot=2)]], "1", True, "SERIAL", "slot exceeds"),
        ([[identifier("A")]], "1", False, "SERIAL", "disabled"),
        ([[identifier("A", "SERIAL")]], "1", True, "IMEI", "not allowed"),
    ],
)
async def test_invalid_serial_rows(monkeypatch, rows, quantity, enabled, kind, message):
    options = SimpleSerialOptions(
        enabled=enabled,
        requirements=[
            {
                "identifier_type": kind,
                "namespace_rule": "COMPANY",
                "min_count": 1,
                "max_count": 1,
                "requires_slot": False,
            }
        ]
        if enabled
        else [],
    )
    monkeypatch.setattr(serials, "serial_options", AsyncMock(return_value=options))
    access = SimpleNamespace(
        reference=AsyncMock(
            return_value=SimpleNamespace(
                dimension="COUNT",
                decimal_places=0,
                quantity_increment=1,
            )
        )
    )
    defaults = SimpleNamespace(
        configuration=None,
        quantity=SimpleNamespace(
            quantity_decimal_places=0,
            quantity_increment=1,
        ),
    )
    body = SimpleCreationInput(
        name="Device",
        base_unit_id=uuid7(),
        purchase_price="10",
        opening_quantity=quantity,
        serials=[{"identifiers": row} for row in rows],
    )
    with pytest.raises(ValidationFailedError, match=message):
        await serials.prepare_serials(access, defaults, body)


def test_empty_serial_addition_preserves_existing_creation_hash_shape():
    body = SimpleCreationInput(
        name="Batch", base_unit_id=uuid7(), batch_enabled=True, batches=[{"code": "LOT"}]
    )
    normalized = creation_request(body)
    assert "serials" not in normalized and "serials" not in normalized["batches"][0]


def test_services_and_too_many_units_rejected():
    unit = {"identifiers": [identifier("A")]}
    with pytest.raises(ValueError, match="Services"):
        SimpleCreationInput(name="Service", kind="SERVICE", base_unit_id=uuid7(), serials=[unit])
    with pytest.raises(ValueError, match="200"):
        SimpleCreationInput(
            name="Batch",
            base_unit_id=uuid7(),
            batch_enabled=True,
            batches=[{"code": "A", "serials": [unit] * 150}, {"code": "B", "serials": [unit] * 51}],
        )
