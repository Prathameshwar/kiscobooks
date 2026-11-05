"""Exact wire precision and native invoice structure, independent of API frameworks."""

from decimal import Decimal

import pytest
from billing_platform.ids import uuid7
from pydantic import TypeAdapter, ValidationError
from voucher_execution.invoice import InvoiceComponent
from voucher_execution.money import Rate


def test_rates_retain_eight_decimals_on_the_shared_wire() -> None:
    assert TypeAdapter(Rate).validate_python("83.12345678") == Decimal("83.12345678")


@pytest.mark.parametrize("value", [1.1, True, "NaN", "0.000000001", "100000000000"])
def test_invalid_rates_are_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Rate).validate_python(value)


def test_percent_components_keep_rate_precision_but_fixed_amounts_do_not() -> None:
    data = {
        "component_key": uuid7(),
        "purpose": "DISCOUNT",
        "scope": "LINE",
        "effect": "DEDUCT",
        "input_kind": "PERCENT",
        "value": "1.12345678",
        "targets": [uuid7()],
        "source_evidence": "Approved trade terms",
    }
    assert InvoiceComponent.model_validate(data).value == Decimal("1.12345678")
    with pytest.raises(ValidationError):
        InvoiceComponent.model_validate(data | {"input_kind": "FIXED"})


def test_invoice_policy_wire_is_stable_across_default_and_explicit_decimals():
    from voucher_execution.invoice import InvoicePolicy

    original = InvoicePolicy()
    transported = InvoicePolicy.model_validate_json(original.model_dump_json())
    assert original.model_dump_json() == transported.model_dump_json()
    explicit = InvoicePolicy(supplier_difference_limit="1.25")
    assert (
        explicit.model_dump_json()
        == InvoicePolicy.model_validate_json(explicit.model_dump_json()).model_dump_json()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"tax_treatment": "NO_CHANGE"},
        {"amount_basis": "GROSS_INCL_TAX"},
        {"tax_allocation_basis": "QUANTITY"},
        {"tax_targets": ["invalid"]},
    ],
)
def test_tax_allocation_requires_unambiguous_net_recipe(changes):
    line = uuid7()
    data = {
        "component_key": uuid7(),
        "purpose": "DISCOUNT",
        "scope": "LINE",
        "effect": "DEDUCT",
        "input_kind": "FIXED",
        "value": "1",
        "targets": [line],
        "tax_targets": [line],
        "source_evidence": "Approved terms",
    }
    assert InvoiceComponent.model_validate(data).tax_targets == (line,)
    with pytest.raises(ValidationError):
        InvoiceComponent.model_validate(data | changes)
