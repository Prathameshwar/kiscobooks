from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from catalog.domain.profiles import (
    HandlingRules,
    IdentifierRequirement,
    InventoryRules,
    ReturnRules,
    WarrantyRules,
    validate_identifier_requirements,
)


def test_identifier_profiles_support_optional_and_multi_slot_requirements() -> None:
    serial = IdentifierRequirement("SERIAL", "MANUFACTURER_SKU", 1, 1, False)
    imei = IdentifierRequirement("IMEI", "COMPANY", 2, 2, True)
    validate_identifier_requirements((serial, imei))
    validate_identifier_requirements((replace(imei, min_count=0),))
    for change in (
        {"identifier_type": "IMEISV"},
        {"namespace_rule": "TENANT"},
        {"min_count": True},
        {"max_count": False},
        {"min_count": -1},
        {"max_count": 0},
        {"max_count": 9},
        {"min_count": 3},
        {"requires_slot": False},
        {"namespace_rule": "MANUFACTURER_SKU"},
        {"requires_slot": 1},
    ):
        with pytest.raises(ValidationFailedError):
            replace(imei, **change)
    for requirements in ((), (serial, serial), (serial, imei, serial)):
        with pytest.raises(ValidationFailedError):
            validate_identifier_requirements(requirements)


def test_inventory_requirements_keep_issue_and_valuation_separate() -> None:
    base = InventoryRules(False, False, False, False, None, None, "FIFO", "MOVING_AVERAGE", False)
    replace(base, serial_tracking=True, valuation_method="SPECIFIC", has_identifier_profile=True)
    expiry = replace(
        base,
        lot_tracking=True,
        expiry_required=True,
        manufacture_date_required=True,
        shelf_life_days=365,
        minimum_remaining_life_days=0,
        issue_strategy="FEFO",
        valuation_method="FIFO",
    )
    assert expiry.issue_strategy == "FEFO" and expiry.valuation_method == "FIFO"
    for change in (
        {"expiry_required": True},
        {"manufacture_date_required": True},
        {"shelf_life_days": 365},
        {"minimum_remaining_life_days": 1},
        {"issue_strategy": "FEFO"},
        {"issue_strategy": "LIFO"},
        {"valuation_method": "LIFO"},
        {"valuation_method": "SPECIFIC"},
        {"has_identifier_profile": True},
        {"serial_tracking": 1},
        {"shelf_life_days": 0},
        {"shelf_life_days": 36501},
    ):
        with pytest.raises(ValidationFailedError):
            replace(base, **change)
    with pytest.raises(ValidationFailedError):
        replace(expiry, minimum_remaining_life_days=366)
    with pytest.raises(ValidationFailedError):
        replace(expiry, expiry_required=False)


def test_warranty_duration_preserves_calendar_units_and_requires_a_trigger() -> None:
    for unit, maximum in (("DAYS", 36500), ("MONTHS", 1200), ("YEARS", 100)):
        for trigger in ("SALE", "DELIVERY", "INSTALLATION"):
            rule = WarrantyRules(maximum, unit, trigger)
            assert rule.duration == maximum and rule.duration_unit == unit
            with pytest.raises(ValidationFailedError):
                replace(rule, duration=maximum + 1)
    for args in (
        (0, "DAYS", "SALE"),
        (True, "DAYS", "SALE"),
        (1, "HOURS", "SALE"),
        (1, "DAYS", "UNKNOWN"),
    ):
        with pytest.raises(ValidationFailedError):
            WarrantyRules(*args)


def test_handling_bounds_are_exact_and_require_explicit_units() -> None:
    empty = HandlingRules(None, None, None, False, False, False)
    chilled = replace(
        empty,
        temperature_min=Decimal("2"),
        temperature_max=Decimal("8"),
        temperature_unit="CELSIUS",
        keep_upright=True,
    )
    assert chilled.temperature_min == Decimal("2")
    replace(chilled, temperature_min=None)
    replace(chilled, temperature_max=None)
    replace(chilled, temperature_min=Decimal("-273.15"))
    for changes in (
        {"temperature_unit": "FAHRENHEIT"},
        {"temperature_unit": None},
        {"temperature_min": Decimal("9")},
        {"temperature_min": Decimal("-273.1501")},
        {"temperature_max": Decimal("NaN")},
        {"temperature_max": Decimal("8.00001")},
        {"temperature_max": 8.1},
        {"fragile": 1},
    ):
        with pytest.raises(ValidationFailedError):
            replace(chilled, **changes)
    with pytest.raises(ValidationFailedError):
        replace(empty, temperature_unit="CELSIUS")


def test_return_windows_and_conditions_are_native_bounded_requirements() -> None:
    ReturnRules(False, None, ())
    ReturnRules(True, 0, ())
    ReturnRules(True, 36500, ("PROOF_OF_PURCHASE", "ORIGINAL_PACKAGING"))
    for args in (
        (False, 0, ()),
        (False, None, ("UNUSED",)),
        (True, None, ()),
        (True, -1, ()),
        (True, True, ()),
        (True, 36501, ()),
        (True, 30, ("CUSTOM_FORMULA",)),
        (True, 30, ("UNUSED", "UNUSED")),
    ):
        with pytest.raises(ValidationFailedError):
            ReturnRules(*args)
