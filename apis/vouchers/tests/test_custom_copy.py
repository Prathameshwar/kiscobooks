import pytest
from billing_platform.custom_fields import CustomDefinition
from billing_platform.errors import PermissionDeniedError, ValidationFailedError

from vouchers.domain.custom_copy import mapped_values


def copy(left, right, values, mapping=None, **authority):
    source, target = {d.key: d for d in left}, {d.key: d for d in right}
    return mapped_values(
        values,
        source,
        target,
        mapping or {"cf_source": "cf_target"},
        readable=authority.get("readable", frozenset(source)),
        writable=authority.get("writable", frozenset(target)),
        currencies=frozenset({"INR"}),
    )


def definition(key, kind="text", **extra):
    return CustomDefinition.model_validate({"key": key, "data_type": kind} | extra)


def test_copy_is_explicit_and_does_not_alias_original_evidence():
    left, right = (
        definition("cf_source", "currency_amount"),
        definition("cf_target", "currency_amount"),
    )
    original = {"cf_source": {"amount": "1.0000", "currency": "INR"}, "cf_other": "secret"}
    copied = copy([left], [right], original)
    assert copied == {"cf_target": original["cf_source"]}
    copied["cf_target"]["amount"] = "2"
    assert original["cf_source"]["amount"] == "1.0000"
    assert copy([left], [right], {}) == {}
    assert copy([left], [right], {"cf_source": None}) == {"cf_target": None}


@pytest.mark.parametrize("authority", [{"readable": frozenset()}, {"writable": frozenset()}])
def test_mapping_cannot_read_or_write_denied_fields(authority):
    with pytest.raises(PermissionDeniedError):
        copy([definition("cf_source")], [definition("cf_target")], {"cf_source": "x"}, **authority)


@pytest.mark.parametrize(
    "target",
    [
        {"data_type": "integer"},
        {"is_active": False},
        {"is_searchable": True, "validation": {"unique_within": "company"}},
        {"depends_on_key": "cf_parent"},
    ],
)
def test_mapping_rejects_incompatible_identity_and_claims(target):
    with pytest.raises(ValidationFailedError):
        copy(
            [definition("cf_source")],
            [CustomDefinition.model_validate({"key": "cf_target", "data_type": "text"} | target)],
            {"cf_source": "x"},
        )


def test_mapping_rejects_auto_number_unknown_definitions_and_repeated_targets():
    left = definition("cf_source", "auto_number", sequence_config={})
    right = definition("cf_target", "auto_number", sequence_config={})
    with pytest.raises(ValidationFailedError):
        copy([left], [right], {"cf_source": "1"})
    with pytest.raises(ValidationFailedError):
        copy([], [right], {}, readable=frozenset({"cf_source"}))
    with pytest.raises(ValidationFailedError):
        copy([left], [right], {}, {"cf_source": "cf_target", "cf_other": "cf_target"})


def test_mapping_revalidates_target_values_and_choices():
    with pytest.raises(ValidationFailedError):
        copy(
            [definition("cf_source")],
            [definition("cf_target", validation={"max_length": 1})],
            {"cf_source": "too long"},
        )
    left = definition("cf_source", "select", choices=[{"value": "A", "label": "A"}])
    right = definition("cf_target", "select", choices=[{"value": "B", "label": "B"}])
    with pytest.raises(ValidationFailedError):
        copy([left], [right], {"cf_source": "A"})
    assert copy([left], [right], {"cf_source": "B"}) == {"cf_target": "B"}
