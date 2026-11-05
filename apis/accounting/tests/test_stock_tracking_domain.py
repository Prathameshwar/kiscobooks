"""Tracking normalization, published identifier rules and date bounds without a database."""

import datetime as dt

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from accounting.domain.stock_tracking import normalized, validate_dates, validate_identifiers
from accounting.schemas.stock_tracking import IdentifierInput, IdentifierRequirement, TrackingSource


def source(**changes):
    return TrackingSource.model_validate(
        {
            "company_id": uuid7(),
            "item_id": uuid7(),
            "profile_revision_id": uuid7(),
            "as_of": "2026-10-28",
            "lot_tracking": True,
            "serial_tracking": True,
            "expiry_required": True,
            "manufacture_date_required": True,
            "source_digest": "a" * 64,
            "requirements": [
                {
                    "identifier_type": "SERIAL",
                    "namespace_rule": "COMPANY",
                    "min_count": 1,
                    "max_count": 1,
                    "requires_slot": False,
                }
            ],
        }
        | changes
    )


def identifier(value="SERIAL-1", **changes):
    return IdentifierInput.model_validate({"identifier_type": "SERIAL", "value": value} | changes)


@pytest.mark.parametrize("value", ["", "   ", "a\x00b", "a\u200db", "a" * 121, "ß" * 61])
def test_identifiers_refuse_blank_controls_and_normalized_overflow(value):
    with pytest.raises(ValidationFailedError):
        normalized(value)


@pytest.mark.parametrize("namespace", ["COMPANY", "MANUFACTURER_SKU"])
def test_normalized_identity_uses_the_published_namespace(namespace):
    rules = source(
        requirements=[
            {
                "identifier_type": "SERIAL",
                "namespace_rule": namespace,
                "min_count": 1,
                "max_count": 1,
                "requires_slot": False,
            }
        ]
    )
    value = identifier("  \uff33\uff25\uff32\uff29\uff21\uff2c-A  ")
    assert validate_identifiers(rules, [value]) == [
        (value, "serial-a", "COMPANY" if namespace == "COMPANY" else str(rules.item_id))
    ]


def test_complete_profile_counts_slots_and_normalized_duplicates_are_enforced():
    rules = source()
    for values in ([], [identifier(slot=2)], [identifier(identifier_type="IMEI")]):
        with pytest.raises(ValidationFailedError):
            validate_identifiers(rules, values)
    slots = source(
        requirements=[
            {
                "identifier_type": "SERIAL",
                "namespace_rule": "COMPANY",
                "min_count": 1,
                "max_count": 2,
                "requires_slot": True,
            }
        ]
    )
    for values in (
        [identifier(), identifier("different")],
        [identifier(), identifier("serial-1", slot=2)],
        [identifier(slot=3)],
    ):
        with pytest.raises(ValidationFailedError):
            validate_identifiers(slots, values)
    assert len(validate_identifiers(slots, [identifier(), identifier("second", slot=2)])) == 2
    for incomplete in (
        source(requirements=[]),
        rules.model_copy(
            update={
                "requirements": rules.requirements * 2,
            }
        ),
    ):
        with pytest.raises(ValidationFailedError):
            validate_identifiers(incomplete, [identifier()])


def test_imei_length_ascii_digits_and_checksum_are_validated():
    requirement = IdentifierRequirement(
        identifier_type="IMEI",
        namespace_rule="COMPANY",
        min_count=1,
        max_count=1,
        requires_slot=False,
    )
    rules = source(requirements=[requirement])
    valid = identifier("490154203237518", identifier_type="IMEI")
    assert validate_identifiers(rules, [valid])[0][1] == valid.value
    for value in ("49015420323751", "49015420323751A", "४९०१५४२०३२३७५१८", "490154203237519"):
        with pytest.raises(ValidationFailedError):
            validate_identifiers(rules, [identifier(value, identifier_type="IMEI")])


def test_required_dates_order_and_published_shelf_life_cannot_be_bypassed():
    manufactured = dt.date(2026, 10, 1)
    expiry = dt.date(2026, 10, 28)
    for start, end in ((None, expiry), (manufactured, None), (expiry, manufactured)):
        with pytest.raises(ValidationFailedError):
            validate_dates(source(), start, end)
    with pytest.raises(ValidationFailedError):
        validate_dates(source(shelf_life_days=10), manufactured, expiry)
    validate_dates(source(shelf_life_days=27), manufactured, expiry)
    validate_dates(source(expiry_required=False, manufacture_date_required=False), None, None)
