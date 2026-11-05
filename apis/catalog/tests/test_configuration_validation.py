import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from catalog.domain.configuration import NumericDefault
from catalog.schemas.configuration import (
    DraftInput,
    DraftPatch,
    NumericInput,
    ProfileDefaults,
    ScopeCreate,
)
from catalog.schemas.product_authoring import ManufacturerAssignmentInput
from catalog.schemas.product_definition_reads import ItemAttributeValueDetail


def test_configuration_pairs_explicit_clears_and_native_scalar_boundaries() -> None:
    for field in (
        "goods_type_revision",
        "service_type_revision",
        "inventory_template_revision",
        "warranty_revision",
        "return_policy_revision",
        "handling_revision",
        "identifier_profile",
    ):
        for invalid in (
            {field + "_mode": "VALUE"},
            {field + "_id": uuid7()},
            {field + "_mode": "CLEAR", field + "_id": uuid7()},
        ):
            with pytest.raises(ValidationError):
                ProfileDefaults.model_validate(invalid)
        assert (
            getattr(ProfileDefaults.model_validate({field + "_mode": "CLEAR"}), field + "_id")
            is None
        )
    with pytest.raises(ValidationError):
        ScopeCreate.model_validate({"scope_kind": "TYPE", "product_type_id": uuid.UUID(int=0)})
    for row in ({"quantity_decimal_places": 2}, {"quantity_increment": "0.25"}):
        with pytest.raises(ValidationError):
            NumericInput.model_validate({"dimension": "TIME", **row})
    for reason in ("   ", "hidden\nline"):
        with pytest.raises(ValidationError):
            DraftInput(scope_id=uuid7(), effective_from=dt.date(2090, 1, 1), change_reason=reason)
    with pytest.raises(ValidationError):
        DraftInput(
            scope_id=uuid7(),
            effective_from=dt.date(2090, 1, 1),
            change_reason="Duplicate",
            numeric_defaults=[NumericInput(dimension="COUNT"), NumericInput(dimension="COUNT")],
        )
    with pytest.raises(ValidationError):
        DraftPatch(expected_version=1, change_reason=None)
    with pytest.raises(ValidationError):
        ManufacturerAssignmentInput(
            expected_version=1,
            manufacturer_id=uuid7(),
            valid_from=dt.date(2091, 1, 1),
            valid_to=dt.date(2090, 1, 1),
        )
    with pytest.raises(ValidationFailedError):
        NumericDefault("COUNT", price_increment=Decimal("1"))
    assert NumericDefault("COUNT", price_decimal_places=2, currency="INR").price_increment is None
    value = ItemAttributeValueDetail.model_validate(
        {
            "id": uuid7(),
            "company_id": uuid7(),
            "created_at": "2090-01-01T00:00:00Z",
            "updated_at": "2090-01-01T00:00:00Z",
            "value_integer": 9223372036854775807,
        }
    )
    assert value.model_dump(mode="json")["value_integer"] == "9223372036854775807"
