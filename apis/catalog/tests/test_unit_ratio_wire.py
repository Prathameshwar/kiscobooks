"""Every public ratio preserves signed BIGINT values for browser consumers."""

import datetime as dt
import json

from billing_platform.ids import uuid7

from catalog.schemas.effective_item import EffectiveUnit
from catalog.schemas.product_authoring import BarcodeResolution


def test_barcode_ratio_is_exact_text_in_json_and_response_schema() -> None:
    value = BarcodeResolution(
        barcode_id=uuid7(),
        matched_value="PACK",
        item_id=uuid7(),
        item_version=1,
        sku="SKU",
        name="Pack",
        unit_id=uuid7(),
        binding_id=uuid7(),
        unit_revision_id=uuid7(),
        usage_role="PACK",
        numerator=9007199254740993,
        denominator=9007199254740995,
    )
    wire = json.loads(value.model_dump_json())
    assert wire["numerator"] == "9007199254740993"
    assert wire["denominator"] == "9007199254740995"
    schema = value.model_json_schema(mode="serialization")["properties"]
    assert schema["numerator"]["type"] == "string"


def test_effective_fixed_and_measured_ratio_wire() -> None:
    value = EffectiveUnit(
        binding_id=uuid7(),
        revision_id=uuid7(),
        revision=1,
        unit_id=uuid7(),
        usage_role="PACK",
        valid_from=dt.date(2026, 1, 1),
        valid_to=None,
        conversion_mode="FIXED",
        numerator=9007199254740993,
        denominator=9007199254740995,
        nominal_ratio=None,
        quantity_decimal_places=0,
        quantity_increment="1",
        fractional_entry=False,
    )
    assert json.loads(value.model_dump_json())["numerator"] == "9007199254740993"
    value.numerator = None
    value.denominator = None
    value.conversion_mode = "MEASURED"
    assert json.loads(value.model_dump_json())["numerator"] is None
