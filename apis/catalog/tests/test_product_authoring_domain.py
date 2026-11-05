import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.money import MoneyError

from catalog.domain.configuration import (
    NumericDefault,
    OptionSetting,
    narrow_quantity_default,
    require_capability,
    resolve_option,
)
from catalog.domain.product_authoring import validate_barcode, variant_identity
from catalog.domain.units import QuantityRule


@pytest.mark.parametrize("value", ["", " x", "x ", "x\n", "é", "x" * 129])
def test_barcode_requires_bounded_exact_ascii(value: str) -> None:
    with pytest.raises(ValidationFailedError):
        validate_barcode(value, "CODE128")


@pytest.mark.parametrize("value", ["4006381333932", "123", "400638133393X"])
def test_gtin_rejects_wrong_check_digit_or_shape(value: str) -> None:
    with pytest.raises(ValidationFailedError):
        validate_barcode(value, "GTIN")


def test_variant_canonical_identity_and_explicit_complete_axes() -> None:
    first, second, blue, small = (uuid.uuid4() for _ in range(4))
    axes = {first: frozenset({blue}), second: frozenset({small})}
    assert variant_identity(axes, {first: blue, second: small}) == variant_identity(
        axes, {second: small, first: blue}
    )
    for selected in ({first: blue}, {first: small, second: blue}, {}):
        with pytest.raises(ValidationFailedError):
            variant_identity(axes, selected)
    with pytest.raises(ValidationFailedError):
        variant_identity({}, {})
    validate_barcode("000-abc", "CODE128")
    validate_barcode("4006381333931", "GTIN")


def test_option_inheritance_hard_requirements_and_capability() -> None:
    with pytest.raises(ValidationFailedError):
        OptionSetting("UNKNOWN")
    with pytest.raises(ValidationFailedError):
        OptionSetting("REQUIRED", True)
    with pytest.raises(ValidationFailedError):
        _ = OptionSetting().enabled
    for baseline, layers in (
        (OptionSetting(), ()),
        (OptionSetting("REQUIRED"), (OptionSetting(),) * 37),
    ):
        with pytest.raises(ValidationFailedError):
            resolve_option(layers, baseline=baseline)
    assert resolve_option((OptionSetting(),), baseline=OptionSetting("DISABLED")).mode == "DISABLED"
    assert resolve_option(
        (OptionSetting("OPTIONAL", True),), baseline=OptionSetting("OPTIONAL", False)
    ).enabled
    for setting, feature, required in (
        (OptionSetting("DISABLED"), True, True),
        (OptionSetting("REQUIRED"), False, False),
        (OptionSetting("OPTIONAL", True), False, False),
        (OptionSetting("OPTIONAL", False), False, True),
    ):
        with pytest.raises(ValidationFailedError):
            require_capability(setting, feature_enabled=feature, required_by_type=required)
    require_capability(OptionSetting("DISABLED"), feature_enabled=False, required_by_type=False)
    require_capability(OptionSetting("REQUIRED"), feature_enabled=True, required_by_type=True)


def test_numeric_defaults_never_round_or_relax_unit_rules() -> None:
    unit = QuantityRule(2, Decimal("0.25"))
    assert narrow_quantity_default(None, unit) == unit
    assert narrow_quantity_default(QuantityRule(1, Decimal("0.1")), unit) == QuantityRule(
        1, Decimal("0.5")
    )
    result = NumericDefault(
        "COUNT",
        price_decimal_places=2,
        price_increment=Decimal("0.05"),
        currency="INR",
        price_basis_quantity=Decimal("100"),
    )
    assert isinstance(result.price_increment, Decimal)
    assert isinstance(result.price_basis_quantity, Decimal)
    invalid_values: tuple[dict[str, Any], ...] = (
        {"dimension": "UNKNOWN"},
        {"currency": "INR"},
        {"price_decimal_places": 2},
        {"price_decimal_places": 2, "currency": "inr"},
        {"price_decimal_places": 2, "currency": "INR", "price_increment": Decimal("0")},
        {"price_decimal_places": 2, "currency": "INR", "price_increment": Decimal("0.001")},
        {"price_basis_quantity": Decimal("0")},
    )
    for values in invalid_values:
        with pytest.raises((ValidationFailedError, MoneyError)):
            NumericDefault(**{"dimension": "COUNT", **values})
