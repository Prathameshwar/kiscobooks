import datetime as dt
from decimal import Decimal

import pytest
from reporting_contract.gst_outward import GstOutwardRecord, OutwardItem

from reports.domain.gstr1_rules import (
    applicable,
    bounds,
    correction_cutoff,
    hsn_digits,
    money,
    threshold,
)


def test_current_and_historical_thresholds_and_turnover_boundaries():
    assert threshold(dt.date(2024, 7, 31)) == Decimal("250000")
    assert threshold(dt.date(2024, 8, 1)) == Decimal("100000")
    assert hsn_digits(Decimal("50000000")) == 4
    assert hsn_digits(Decimal("50000000.01")) == 6
    assert money(Decimal("0.0050")) == "0.01"


def test_explicit_india_and_supplier_registration_required():
    assert applicable({"country_code": "IN", "tax_system": "gst_in", "regime": "regular"})
    for extra in ({"country_code": "US"}, {"regime": "composition"}, {"registration_class": "tcs"}):
        assert not applicable(
            {"country_code": "IN", "tax_system": "gst_in", "regime": "regular"} | extra
        )
    assert not applicable({"tax_system": "gst_in", "regime": "regular"})


def test_statutory_periods_and_credit_note_cutoff():
    assert bounds("2026-Q1", "QRMP") == (dt.date(2026, 1, 1), dt.date(2026, 3, 31))
    with pytest.raises(ValueError):
        bounds("2024-08", "MONTHLY")
    assert correction_cutoff(dt.date(2025, 4, 1), None) == dt.date(2026, 11, 30)
    assert correction_cutoff(dt.date(2026, 1, 1), dt.date(2026, 9, 30)) == dt.date(2026, 9, 30)


@pytest.mark.parametrize("bad", [1.1, True, "NaN", "-1", "0.00001"])
def test_wire_money_and_quantities_are_exact_and_positive(bad):
    with pytest.raises(ValueError):
        OutwardItem(quantity=bad)


def test_document_totals_cannot_disagree_with_details():
    import uuid

    value = {
        "registration_id": str(uuid.uuid4()),
        "return_date": "2026-10-01",
        "document_date": "2026-10-01",
        "kind": "INVOICE",
        "document_number": "INV/1",
        "source_entity": "EXTERNAL",
        "reference": "retained invoice",
        "evidence_hash": "a" * 64,
        "explanation": "Reviewed retained invoice",
        "invoice_value": "118",
        "details": {
            "place_of_supply": "29",
            "items": [{"taxable": "100", "igst": "18", "rate": "18"}],
        },
    }
    assert GstOutwardRecord.model_validate(value).taxable == "100.0000"
    with pytest.raises(ValueError, match="totals"):
        GstOutwardRecord.model_validate(value | {"igst": "1"})
