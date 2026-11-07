"""Validate the ten captured UI request bodies against native Simple input schemas.

These fixtures are component simulations, not evidence that reference masters or
owner services were provisioned. Native policy/persistence has separate tests.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from catalog.schemas.simple_product_creation import SimpleCreationInput

CASES = json.loads(
    (Path(__file__).parent / "fixtures/simple_config_client_bodies.json").read_text()
)
INPUTS = {row["scenario"]: row["body"] for row in CASES}


@pytest.mark.parametrize("row", CASES, ids=lambda row: f"S{row['scenario']:02}")
def test_captured_simple_client_body_matches_native_contract(row):
    body = SimpleCreationInput.model_validate(row["body"])
    assert body.kind == ("SERVICE" if row["scenario"] == 5 else "GOODS")
    assert isinstance(body.opening_quantity, Decimal)
    assert len(CASES) == 10 and set(INPUTS) == set(range(1, 11))
    if body.purchase_price is not None:
        assert isinstance(body.purchase_price, Decimal)
    expected = {2: Decimal("1600"), 7: Decimal("1600"), 8: Decimal("40000"), 9: Decimal("524.6625")}
    if row["scenario"] in expected:
        if body.batches:
            valuation = sum(
                batch.opening_quantity * batch.opening_unit_cost for batch in body.batches
            )
        else:
            valuation = body.opening_quantity * body.opening_unit_cost
        assert valuation == expected[row["scenario"]]
        assert isinstance(valuation, Decimal)


def negatives():
    for number, body in INPUTS.items():
        yield f"S{number:02}-empty-name", body | {"name": ""}
    for number in (2, 6, 9):
        yield f"S{number:02}-zero-purchase", INPUTS[number] | {"purchase_price": "0"}
    for number in (2, 5, 9):
        yield f"S{number:02}-negative-sale", INPUTS[number] | {"sale_price": "-1"}
    for number in (2, 8, 9):
        yield f"S{number:02}-negative-quantity", INPUTS[number] | {"opening_quantity": "-1"}
        yield f"S{number:02}-zero-cost", INPUTS[number] | {"opening_unit_cost": "0"}
    yield "S02-zero-mrp", INPUTS[2] | {"mrp": "0"}
    yield "S05-service-stock", INPUTS[5] | {"opening_quantity": "1", "opening_unit_cost": "80"}
    yield (
        "S04-series-without-brand",
        INPUTS[4] | {"brand_id": None, "series_id": INPUTS[4]["brand_id"]},
    )
    yield (
        "S04-site-without-maker",
        INPUTS[4] | {"manufacturer_id": None, "manufacturer_site_id": INPUTS[4]["manufacturer_id"]},
    )
    yield "S06-mixed-sale-inputs", INPUTS[6] | {"sale_price": "100"}
    yield "S06-duplicate-level", INPUTS[6] | {"sale_prices": [INPUTS[6]["sale_prices"][0]] * 2}
    batch = INPUTS[7]["batches"][0]
    yield "S07-65-batches", INPUTS[7] | {"batches": [batch | {"code": str(i)} for i in range(65)]}
    yield "S07-invalid-date", INPUTS[7] | {"batches": [batch | {"expires_on": "2026-02-30"}]}
    yield (
        "S07-expiry-before-manufacture",
        INPUTS[7] | {"batches": [batch | {"expires_on": "2025-01-01"}]},
    )
    yield (
        "S07-normalized-duplicate",
        INPUTS[7] | {"batches": [batch | {"code": "Straße"}, batch | {"code": "STRASSE"}]},
    )
    yield "S07-empty-code", INPUTS[7] | {"batches": [batch | {"code": ""}]}
    yield (
        "S07-missing-valuation",
        INPUTS[7] | {"batches": [batch | {"opening_unit_cost": None, "purchase_price": None}]},
    )
    yield (
        "S08-201-serials",
        INPUTS[8] | {"serials": INPUTS[8]["serials"][:1] * 201, "opening_quantity": "201"},
    )


@pytest.mark.parametrize(
    "name, body", list(negatives()), ids=lambda value: value if isinstance(value, str) else None
)
def test_invalid_simple_client_input_is_rejected(name, body):
    with pytest.raises(ValidationError):
        SimpleCreationInput.model_validate(copy.deepcopy(body))
