"""The Purchase print facts contract grows additively: an older owner's reply still validates."""

import json
import uuid

import pytest
from pydantic import ValidationError

from voucher_execution.invoice import InvoiceCalculationDetail
from voucher_execution.printing import PrintLedger, PrintLine, PurchasePrintFacts


def calculation() -> dict[str, object]:
    line = str(uuid.uuid4())
    return {
        "currency": "INR",
        "calculation_hash": "a" * 64,
        "commercial_total": "10.0000",
        "tax_total": "0.0000",
        "charged_tax_total": "0.0000",
        "rounding": "0.0000",
        "payable": "10.0000",
        "lines": [
            {
                "key": line,
                "entered": "10.0000",
                "commercial": "10.0000",
                "taxable": "10.0000",
                "taxes": [],
                "price_rounding": "0.0000",
                "payable": "10.0000",
            }
        ],
        "components": [],
        "allocations": [],
        "tax_evidence": [],
    }


def facts(**extra: object) -> PurchasePrintFacts:
    return PurchasePrintFacts.model_validate(
        {"calculation": calculation(), "supplier_name": "Supplier", "source": "PREVIEW"}
        | extra
    )


def test_a_reply_without_the_new_fields_still_validates_with_neutral_defaults():
    old = facts()
    assert old.voucher_number is None and old.ledgers == () and old.lines == ()
    assert isinstance(old.calculation, InvoiceCalculationDetail)


def test_the_voucher_number_and_ledgers_round_trip_through_the_wire_form():
    key = uuid.uuid4()
    sent = facts(
        source="POSTED",
        voucher_number="PURCHASE/FY2026-2027/000002",
        ledgers=[
            {"key": str(key), "name": "Rent"},
            {"key": str(uuid.uuid4()), "name": None},
        ],
    )
    received = PurchasePrintFacts.model_validate_json(sent.model_dump_json())
    assert received == sent
    assert received.ledgers[0] == PrintLedger(key=key, name="Rent")
    assert (
        json.loads(sent.model_dump_json())["voucher_number"]
        == "PURCHASE/FY2026-2027/000002"
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"voucher_number": ""},
        {"voucher_number": "N" * 101},
        {"ledgers": [{"key": str(uuid.uuid4()), "name": ""}]},
        {"ledgers": [{"key": str(uuid.uuid4()), "name": "L" * 201}]},
        {"ledgers": [{"key": str(uuid.uuid4())} for _ in range(401)]},
        {"ledgers": [{"key": str(uuid.uuid4()), "name": "x", "extra": 1}]},
        {"lines": [{"key": str(uuid.uuid4()), "classification_code": "04A2"}]},
        {"lines": [{"key": str(uuid.uuid4()), "classification_code": "040"}]},
        {"lines": [{"key": str(uuid.uuid4()), "unit_label": ""}]},
        {"lines": [{"key": str(uuid.uuid4()), "unit_label": "u" * 21}]},
        {"lines": [{"key": str(uuid.uuid4())} for _ in range(201)]},
        {"unexpected": True},
    ],
)
def test_out_of_bound_or_unknown_values_are_refused(extra):
    with pytest.raises(ValidationError):
        facts(**extra)


def test_facts_are_immutable():
    with pytest.raises(ValidationError):
        facts().voucher_number = "X"  # type: ignore[misc]


def test_line_labels_round_trip_and_default_to_nothing():
    key = uuid.uuid4()
    sent = facts(lines=[{"key": str(key), "classification_code": "0402", "unit_label": "kg"}])
    assert PurchasePrintFacts.model_validate_json(sent.model_dump_json()) == sent
    assert PrintLine(key=key) == PrintLine(key=key, classification_code=None, unit_label=None)


def test_stock_labels_are_asked_for_and_answered_only_when_wanted():
    from voucher_execution.stock_facts import StockFenceRequest, StockItemFact

    assert "include_labels" in StockFenceRequest.model_fields
    assert StockItemFact.model_fields["base_unit_label"].default is None
