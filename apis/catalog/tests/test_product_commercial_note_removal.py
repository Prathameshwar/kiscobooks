"""The retired creation note is rejected rather than hidden or stored implicitly."""

import uuid

import pytest
from pydantic import ValidationError

from catalog.domain.field_registry import registry
from catalog.models.pricing import ItemPrice, ItemPriceDraft
from catalog.models.tax import CatalogTaxBinding, TaxRate
from catalog.schemas.pricing import DraftInput
from catalog.schemas.pricing_reads import ItemPriceDetail, ItemPriceDraftDetail
from catalog.schemas.product_initial import InitialPrice, InitialTax
from catalog.schemas.tax import BindingInput
from catalog.schemas.tax_governance import ReleaseBinding
from catalog.schemas.tax_reads import CatalogTaxBindingDetail


@pytest.mark.parametrize(
    ("schema", "values"),
    [
        (InitialTax, {"rule_id": uuid.uuid4(), "directions": ["SALE"]}),
        (
            InitialPrice,
            {
                "plan_id": uuid.uuid4(),
                "amount": "12.34",
                "price_basis_quantity": "1",
                "price_decimal_places": 2,
            },
        ),
        (
            DraftInput,
            {
                "series_id": uuid.uuid4(),
                "numeric_revision_id": uuid.uuid4(),
                "valid_from": "2026-10-30",
                "price_method": "FIXED",
                "amount": "12.34",
                "price_basis_quantity": "1",
            },
        ),
        (
            BindingInput,
            {
                "scope_id": uuid.uuid4(),
                "expected_generation": 1,
                "expected_source_version": 1,
                "valid_from": "2026-10-30",
                "direction": "SALE",
                "bundle": "RULE",
                "mode": "OVERRIDE",
                "rule_id": uuid.uuid4(),
            },
        ),
        (
            ReleaseBinding,
            {
                "scope_id": uuid.uuid4(),
                "expected_generation": 1,
                "expected_source_version": 1,
                "valid_from": "2026-10-30",
                "direction": "SALE",
                "bundle": "RULE",
                "mode": "OVERRIDE",
                "rule_id": uuid.uuid4(),
            },
        ),
        (
            ReleaseBinding,
            {
                "scope_id": uuid.uuid4(),
                "expected_generation": 1,
                "expected_source_version": 1,
                "valid_from": "2026-10-30",
                "direction": "PURCHASE",
                "bundle": "CLASSIFICATION",
                "mode": "OVERRIDE",
                "classification_id": {"key": "classification"},
            },
        ),
    ],
)
def test_note_is_not_required_and_retired_input_is_rejected(schema, values):
    assert "source_reference" not in schema.model_validate(values).model_dump()
    with pytest.raises(ValidationError) as error:
        schema.model_validate({**values, "source_reference": "Retired note"})
    assert any(entry["type"] == "extra_forbidden" for entry in error.value.errors())


def test_note_is_removed_from_storage_but_statutory_evidence_remains():
    for model in (CatalogTaxBinding, ItemPriceDraft, ItemPrice):
        assert "source_reference" not in model.__table__.columns
    assert "source_reference" in TaxRate.__table__.columns


@pytest.mark.parametrize(
    ("entity", "detail"),
    [
        ("catalog.catalog_tax_binding", CatalogTaxBindingDetail),
        ("catalog.item_price_draft", ItemPriceDraftDetail),
        ("catalog.item_price", ItemPriceDetail),
    ],
)
def test_detail_and_form_metadata_do_not_expose_the_note(entity, detail):
    assert "source_reference" not in detail.model_fields
    assert "source_reference" not in registry.get(entity).fields
