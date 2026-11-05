"""Physical observations are separate from their calculated stock variance."""

import uuid

import pytest
from pydantic import ValidationError

from voucher_execution.stock import StockInput


def payload(action="COUNT"):
    return {
        "action": action,
        "stock_date": "2026-10-31",
        "currency": "INR",
        "reason": "Reviewed physical count",
        "lines": [{
            "line_id": str(uuid.uuid4()), "item_id": str(uuid.uuid4()),
            "warehouse_id": str(uuid.uuid4()), "quantity": "0",
            "count": {"observation_id": str(uuid.uuid4()), "expected_revision": 2},
        }],
    }


def test_count_zero_is_an_explicit_observation():
    assert StockInput.model_validate(payload()).lines[0].quantity == 0


def test_count_requires_native_observation_and_cannot_be_a_receipt():
    body = payload()
    del body["lines"][0]["count"]
    with pytest.raises(ValidationError):
        StockInput.model_validate(body)
    body = payload("RECEIPT")
    body["lines"][0].update(quantity="1", received_value="1")
    with pytest.raises(ValidationError):
        StockInput.model_validate(body)
