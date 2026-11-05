"""Closed product field and dependent option-source contracts."""

import pytest
from billing_platform.custom_fields import CustomDefinition
from billing_platform.errors import ValidationFailedError

from identity.domain import catalog_fields


def test_unknown_product_and_native_field_are_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        catalog_fields.contract("catalog.unknown")
    with pytest.raises(ValidationFailedError):
        catalog_fields.native_field("catalog.item", "unknown")


def test_registered_dynamic_parent_is_required_and_validated() -> None:
    parent = CustomDefinition(
        key="cf_scheme", data_type="dynamic_select", option_source_key="catalog.category_schemes"
    )
    child = CustomDefinition(
        key="cf_category",
        data_type="dynamic_select",
        option_source_key="catalog.item_categories",
        depends_on_key="cf_scheme",
    )
    catalog_fields.validate_options("catalog.item", (parent, child))
    with pytest.raises(ValidationFailedError):
        catalog_fields.validate_options("catalog.item", (child,))
    with pytest.raises(ValidationFailedError):
        catalog_fields.validate_options(
            "catalog.item", (parent.model_copy(update={"depends_on_key": "cf_category"}), child)
        )
