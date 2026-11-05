import datetime as dt
import uuid
from dataclasses import replace
from decimal import Decimal, localcontext
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.exact import RationalConversion
from billing_platform.ids import uuid7

from catalog.domain.attributes import AttributeValue, DefinitionRules, MemberRule, validate_members


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("TEXT", "Blue"),
        ("INTEGER", 0),
        ("INTEGER", -(2**63)),
        ("DECIMAL", "0.0001"),
        ("BOOLEAN", False),
        ("DATE", dt.date(2026, 1, 1)),
    ],
)
def test_native_values_are_typed_and_canonical(kind: str, value: Any) -> None:
    parsed = AttributeValue(kind, value)
    parsed.validate_definition(DefinitionRules(kind, None, True))
    digest, canonical = parsed.canonical()
    assert len(digest) == 32 and canonical


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("TEXT", " "),
        ("TEXT", "\ud800"),
        ("TEXT", "x" * 201),
        ("TEXT", "a\nb"),
        ("INTEGER", True),
        ("INTEGER", 2**63),
        ("INTEGER", "1"),
        ("DECIMAL", 0.1),
        ("DECIMAL", "NaN"),
        ("DECIMAL", "0.00001"),
        ("BOOLEAN", 1),
        ("DATE", dt.datetime(2026, 1, 1)),
        ("DATE", dt.date(999, 1, 1)),
        ("UNKNOWN", "x"),
    ],
)
def test_invalid_native_representations_are_rejected(kind: str, value: Any) -> None:
    with pytest.raises(ValidationFailedError):
        AttributeValue(kind, value)


def test_text_and_numeric_equality_is_explicit_and_context_independent() -> None:
    assert (
        AttributeValue("TEXT", " BLUE ").canonical() == AttributeValue("TEXT", "Blue").canonical()
    )
    assert AttributeValue("TEXT", "\uff21").canonical() == AttributeValue("TEXT", "a").canonical()
    with localcontext() as context:
        context.prec = 2
        assert (
            AttributeValue("DECIMAL", "12345.6700").canonical()
            == AttributeValue("DECIMAL", Decimal("12345.67")).canonical()
        )
        assert (
            AttributeValue("DECIMAL", "-0.0000").canonical()
            == AttributeValue("DECIMAL", "0").canonical()
        )
    # Unicode compatibility expansion still has to fit the persistent comparison payload.
    with pytest.raises(ValidationFailedError, match="bounds"):
        AttributeValue("TEXT", "\ufdfa" * 200).canonical()


def test_measured_values_use_verified_canonical_conversion_evidence() -> None:
    gram, kilogram = uuid7(), uuid7()
    small = AttributeValue("DECIMAL", "1000", gram)
    large = AttributeValue("DECIMAL", "1", kilogram)
    small.validate_definition(DefinitionRules("DECIMAL", "MASS", True))
    assert small.canonical(
        canonical_unit_id=kilogram, conversion=RationalConversion(1, 1000)
    ) == large.canonical(canonical_unit_id=kilogram, conversion=RationalConversion(1, 1))
    with pytest.raises(ValidationFailedError):
        small.canonical()
    with pytest.raises(ValidationFailedError):
        large.canonical(canonical_unit_id=kilogram)
    with pytest.raises(ValidationFailedError):
        AttributeValue("DECIMAL", "1").canonical(
            canonical_unit_id=kilogram, conversion=RationalConversion(1, 1)
        )
    with pytest.raises(ValidationFailedError):
        small.validate_definition(DefinitionRules("INTEGER", "MASS", True))
    with pytest.raises(ValidationFailedError):
        small.validate_definition(DefinitionRules("DECIMAL", None, True))
    for kind, value, unit in [("TEXT", "X", gram), ("INTEGER", 1, uuid.UUID(int=0))]:
        with pytest.raises(ValidationFailedError):
            AttributeValue(kind, value, unit)


def test_definition_and_template_contracts_are_bounded_and_compatible() -> None:
    invalid_definitions: list[tuple[str, str | None, Any]] = [
        ("UNKNOWN", None, True),
        ("TEXT", "MASS", True),
        ("DECIMAL", "VOLTAGE", True),
        ("TEXT", None, 1),
    ]
    for args in invalid_definitions:
        with pytest.raises(ValidationFailedError):
            DefinitionRules(*args)
    identity, other = uuid7(), uuid7()
    definition = DefinitionRules("TEXT", None, True)
    member = MemberRule(identity, 0, True, True)
    validate_members((member,), {identity: definition})
    validate_members((), {}, allow_empty=True)
    for members, definitions in [
        ((), {}),
        ((member, member), {identity: definition}),
        ((member, replace(member, definition_id=other)), {identity: definition, other: definition}),
        ((member,), {}),
        ((member,), {identity: replace(definition, is_active=False)}),
        ((member,), {identity: replace(definition, is_variant_capable=False)}),
        ((member,) * 129, {identity: definition}),
    ]:
        with pytest.raises(ValidationFailedError):
            validate_members(members, definitions)
    for changes in (
        {"definition_id": uuid.UUID(int=0)},
        {"position": 128},
        {"position": True},
        {"is_required": 1},
        {"allow_variant_axis": 0},
    ):
        with pytest.raises(ValidationFailedError):
            replace(member, **changes)


def test_integer_transport_preserves_native_write_values() -> None:
    from catalog.schemas.attributes import AttributeOptionCreate

    option = AttributeOptionCreate.model_validate(
        {
            "code": "LARGE",
            "name": "Large",
            "definition_id": uuid7(),
            "value_type": "INTEGER",
            "value_integer": "9007199254740993",
        }
    )
    assert option.value_integer == 9007199254740993
    assert type(option.model_dump()["value_integer"]) is int
    assert option.model_dump(mode="json")["value_integer"] == "9007199254740993"


@pytest.mark.parametrize(
    "changes",
    [
        {"value_integer": True},
        {"value_integer": 0.5},
        {"value_integer": "01"},
        {"value_integer": str(2**63)},
        {"value_integer": None},
        {"value_text": "wrong"},
    ],
)
def test_attribute_option_wire_rejects_ambiguous_integer_values(changes: dict[str, Any]) -> None:
    from pydantic import ValidationError

    from catalog.schemas.attributes import AttributeOptionCreate

    with pytest.raises(ValidationError):
        AttributeOptionCreate.model_validate(
            {
                "code": "N",
                "name": "Number",
                "definition_id": uuid7(),
                "value_type": "INTEGER",
                "value_integer": "1",
                **changes,
            }
        )


def test_attribute_wire_decimal_boolean_and_protected_partial_details() -> None:
    from pydantic import ValidationError

    from catalog.schemas.attributes import (
        AttributeDefinitionCreate,
        AttributeOptionCreate,
        AttributeOptionDetail,
    )

    base = {"code": "V", "name": "Value", "definition_id": uuid7()}
    for kind, field, value in [
        ("DECIMAL", "value_decimal", "0.0001"),
        ("BOOLEAN", "value_boolean", False),
        ("DATE", "value_date", "2026-01-01"),
        ("TEXT", "value_text", "Blue"),
    ]:
        item = AttributeOptionCreate.model_validate({**base, "value_type": kind, field: value})
        assert item.model_dump()[field] is not None
    with pytest.raises(ValidationError):
        AttributeOptionCreate.model_validate(
            {**base, "value_type": "DECIMAL", "value_decimal": 0.1}
        )
    assert (
        AttributeDefinitionCreate.model_validate(
            {
                "code": "D",
                "name": "Definition",
                "value_type": "DECIMAL",
                "measurement_dimension": "MASS",
            }
        ).measurement_dimension
        == "MASS"
    )
    partial = AttributeOptionDetail.model_validate(
        {
            "id": uuid7(),
            "company_id": uuid7(),
            "created_at": dt.datetime.now(dt.UTC),
            "updated_at": dt.datetime.now(dt.UTC),
            "policy_generation": 1,
        }
    )
    assert "value_integer" not in partial.model_dump(exclude_unset=True)


def test_native_attribute_policy_numbers_keep_signed_bigint_range() -> None:
    from catalog.tasks.field_context import NUMERIC_FIELDS, condition_scalar

    for value in (str(-(2**63)), "9007199254740993", str(2**63 - 1)):
        normalized = condition_scalar("value_integer", value, NUMERIC_FIELDS)
        assert isinstance(normalized, Decimal) and normalized == Decimal(value)
    for value in (str(-(2**63) - 1), str(2**63)):
        with pytest.raises(ValueError):
            condition_scalar("value_integer", value, NUMERIC_FIELDS)


def test_attribute_labels_reject_unencodable_surrogates() -> None:
    from pydantic import ValidationError

    from catalog.schemas.attributes import AttributeDefinitionCreate

    with pytest.raises(ValidationError):
        AttributeDefinitionCreate(code="TEXT", name="\ud800", value_type="TEXT")


def test_exact_unit_increment_updates_preserve_decimal_type() -> None:
    from pydantic import ValidationError

    from catalog.schemas.units import UnitUpdate

    update = UnitUpdate.model_validate({"expected_version": 1, "quantity_increment": "0.125"})
    assert isinstance(update.quantity_increment, Decimal) and update.quantity_increment == Decimal(
        "0.125"
    )
    with pytest.raises(ValidationError):
        UnitUpdate.model_validate({"expected_version": 1, "quantity_increment": 0.125})
