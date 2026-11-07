import pytest
from billing_platform.errors import ValidationFailedError
from voucher_execution.identifiers import IdentifierRequirement

from catalog.schemas.advanced_product_creation import AdvancedOpeningInput
from catalog.tasks import advanced_creation_opening


@pytest.mark.parametrize("batch", [False, True])
def test_serial_opening_error_keeps_physical_row_path(batch: bool) -> None:
    identifiers = [{"identifier_type": "IMEI", "value": "123456789012345"}]
    entry = {
        "opening_quantity": "1",
        "purchase_price": "10",
        "serials": [{"identifiers": identifiers}],
    }
    body = {"decision": "OPEN", "opening_date": "2026-11-07"}
    if batch:
        body["batches"] = [{"code": "LOT", **entry}]
    else:
        body.update(entry)
    opening = AdvancedOpeningInput.model_validate(body)
    validate = getattr(advanced_creation_opening, "validate_opening_identifiers", None)
    assert callable(validate), "Native opening errors need a physical-row validator"
    rule = IdentifierRequirement(
        identifier_type="IMEI",
        namespace_rule="COMPANY",
        min_count=1,
        max_count=1,
        requires_slot=False,
    )
    with pytest.raises(ValidationFailedError) as failure:
        validate(opening, [rule])
    path = "batches.0.serials.0.identifiers" if batch else "serials.0.identifiers"
    assert failure.value.extra.get("fields") == {path: "IMEI checksum is invalid"}
