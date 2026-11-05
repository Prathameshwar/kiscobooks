from dataclasses import replace
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from catalog.domain.product_types import TypeRequirements
from catalog.domain.profiles import InventoryRules
from catalog.schemas.commercial import BrandManufacturerCreate, TypeRevisionInput

BASE = TypeRequirements("GOODS", frozenset({"STOCK"}), frozenset({"NONE"}), frozenset({"COUNT"}))


def test_profile_defaults_admit_compatible_stock_and_preserve_service_separation() -> None:
    stock = InventoryRules(False, False, False, False, None, None, "FIFO", "FIFO", False)
    for lot, serial, tracking in (
        (False, False, "NONE"),
        (True, False, "BATCH"),
        (False, True, "SERIAL"),
        (True, True, "BATCH_SERIAL"),
    ):
        rules = replace(BASE, tracking_modes=frozenset({tracking}))
        rules.validate_profile_defaults(
            inventory=replace(stock, lot_tracking=lot, serial_tracking=serial), has_handling=True
        )
    service = replace(BASE, kind="SERVICE", inventory_modes=frozenset({"NON_STOCK"}))
    mixed = replace(BASE, kind="BOTH", inventory_modes=frozenset({"STOCK", "NON_STOCK"}))
    for rules in (service, mixed):
        rules.validate_profile_defaults(inventory=None, has_handling=False)
        for physical, handling in ((stock, False), (None, True)):
            with pytest.raises(ValidationFailedError, match="goods-only"):
                rules.validate_profile_defaults(inventory=physical, has_handling=handling)
    for rules in (
        replace(BASE, inventory_modes=frozenset({"NON_STOCK"})),
        replace(BASE, tracking_modes=frozenset({"BATCH"})),
    ):
        with pytest.raises(ValidationFailedError, match="allowed modes"):
            rules.validate_profile_defaults(inventory=stock, has_handling=False)
    expiry = replace(BASE, tracking_modes=frozenset({"BATCH"}), require_expiry=True)
    with pytest.raises(ValidationFailedError, match="mandatory expiry"):
        expiry.validate_profile_defaults(
            inventory=replace(stock, lot_tracking=True), has_handling=False
        )
    expiry.validate_profile_defaults(
        inventory=replace(stock, lot_tracking=True, expiry_required=True), has_handling=False
    )


def test_goods_services_and_batch_serial_requirements() -> None:
    assert replace(BASE, require_manufacturer=True).require_manufacturer
    service = replace(
        BASE,
        kind="SERVICE",
        inventory_modes=frozenset({"NON_STOCK"}),
        unit_dimensions=frozenset({"TIME", "JOB", "MASS"}),
        require_brand=True,
    )
    assert service.require_brand
    mixed = replace(BASE, kind="BOTH", inventory_modes=frozenset({"NON_STOCK", "STOCK"}))
    assert mixed.kind == "BOTH"
    expiry = replace(BASE, tracking_modes=frozenset({"BATCH", "BATCH_SERIAL"}), require_expiry=True)
    assert expiry.require_expiry
    assert replace(BASE, tracking_modes=frozenset({"SERIAL"})).unit_dimensions == {"COUNT"}


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "UNSUPPORTED"},
        {"unit_dimensions": frozenset()},
        {"inventory_modes": frozenset({"MAGIC"})},
        {"tracking_modes": frozenset({"MAGIC"})},
        {"allow_variants": 1},
        {"kind": "SERVICE"},
        {
            "kind": "SERVICE",
            "inventory_modes": frozenset({"NON_STOCK"}),
            "require_manufacturer": True,
        },
        {"kind": "BOTH"},
        {
            "inventory_modes": frozenset({"NON_STOCK", "STOCK"}),
            "tracking_modes": frozenset({"BATCH"}),
        },
        {
            "inventory_modes": frozenset({"NON_STOCK"}),
            "tracking_modes": frozenset({"NONE", "BATCH"}),
        },
        {"tracking_modes": frozenset({"SERIAL"}), "unit_dimensions": frozenset({"MASS"})},
        {"tracking_modes": frozenset({"SERIAL"}), "unit_dimensions": frozenset({"MASS", "COUNT"})},
        {"require_expiry": True},
    ],
)
def test_impossible_or_unsupported_type_contracts_are_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        replace(BASE, **changes)


def test_requirement_wire_normalization_and_invalid_relationship_dates() -> None:
    body = {
        "inventory_modes": ["STOCK", "NON_STOCK"],
        "tracking_modes": ["NONE"],
        "unit_dimensions": ["TIME", "COUNT"],
    }
    result = TypeRevisionInput.model_validate(body)
    assert result.inventory_modes == ("NON_STOCK", "STOCK")
    assert result.unit_dimensions == ("COUNT", "TIME")
    invalid_changes: tuple[dict[str, Any], ...] = (
        {"inventory_modes": ["STOCK", "STOCK"]},
        {"require_expiry": 1},
        {"tracking_modes": []},
        {"unknown": True},
    )
    for changes in invalid_changes:
        with pytest.raises(ValidationError):
            TypeRevisionInput.model_validate({**body, **changes})
    relation = {
        "brand_id": "01900000-0000-7000-8000-000000000001",
        "manufacturer_id": "01900000-0000-7000-8000-000000000002",
        "production_role": "OEM",
        "valid_from": "2025-02-01",
    }
    assert BrandManufacturerCreate.model_validate(relation).valid_to is None
    with pytest.raises(ValidationError):
        BrandManufacturerCreate.model_validate({**relation, "valid_to": "2025-01-31"})
