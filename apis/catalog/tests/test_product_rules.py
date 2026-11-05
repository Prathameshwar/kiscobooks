from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from catalog.domain.products import validate_structure
from catalog.domain.units import QuantityRule
from catalog.schemas.products import FamilyPatch, ItemInput, ItemPatch


def test_product_kind_dimension_and_exact_quantities() -> None:
    common: dict[str, Any] = {
        "kind": "SERVICE",
        "type_kind": "BOTH",
        "dimension": "TIME",
        "allowed_dimensions": ("TIME",),
        "quantity": QuantityRule(2, Decimal("0.25")),
        "minimum_sale": Decimal("0.75"),
    }
    validate_structure(**common)
    validate_structure(**{**common, "minimum_sale": None})
    for bad in (
        {"kind": "OTHER"},
        {"type_kind": "GOODS"},
        {"dimension": "MASS"},
        {"minimum_sale": Decimal("0")},
        {"minimum_sale": Decimal("-1")},
        {"minimum_sale": Decimal("0.10")},
    ):
        with pytest.raises(ValidationFailedError):
            validate_structure(**{**common, **bad})
    for minimum in (1.2, "0", "-1", "0.00001", "NaN", True):
        with pytest.raises(ValidationError):
            ItemInput.model_validate(
                {
                    "sku": "SKU",
                    "name": "Product",
                    "base_unit_id": "00000000-0000-0000-0000-000000000001",
                    "min_sale_quantity": minimum,
                }
            )
    for schema, field in ((ItemPatch, "sellable"), (ItemPatch, "name"), (FamilyPatch, "code")):
        with pytest.raises(ValidationError):
            schema.model_validate({"expected_version": 1, field: None})
