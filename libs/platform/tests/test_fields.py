"""Native field registry and ``field_config`` write-time guards.

The line these tests defend: **hiding is layout, not authorization.** A tenant
admin arranging a form must never be able to loosen a domain rule, drop a
statutory field, or change who may see something — that last one is
``field_policy``'s job and stays a separate step in the resolver.
"""

from __future__ import annotations

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.fields import (
    EntityFields,
    FieldRegistry,
    NativeField,
    assert_config_allowed,
)
from tests.models import TenantThing


def _registry() -> FieldRegistry:
    reg = FieldRegistry()
    reg.register(
        EntityFields(
            entity_type="tests.thing",
            model_name="TenantThing",
            fields={
                "name": NativeField(
                    required=True,
                    hideable=False,
                    renameable=False,
                    reason="prints on statutory output under its legal name",
                ),
                "currency": NativeField(
                    required=False,
                    hideable=False,
                    reason="drives money; a hidden currency is an unpriced document",
                ),
                "qty": NativeField(group="lines", order=10),
                "amount": NativeField(requires_feature="pricing"),
            },
        )
    )
    return reg


def test_non_hideable_field_must_state_a_reason() -> None:
    """Otherwise the rejection message cannot explain itself to the admin."""
    with pytest.raises(ValueError, match="must state a reason"):
        NativeField(hideable=False)


def test_defaults_are_optional_hideable_renameable() -> None:
    plain = NativeField()
    assert (plain.required, plain.hideable, plain.renameable) == (False, True, True)
    assert plain.requires_feature is None


def test_register_rejects_a_duplicate_entity_type() -> None:
    reg = _registry()
    with pytest.raises(ValueError, match="already registered"):
        reg.register(EntityFields(entity_type="tests.thing", model_name="TenantThing"))


def test_entity_types_are_listed_sorted() -> None:
    reg = _registry()
    reg.register(EntityFields(entity_type="tests.another", model_name="TenantThing"))
    assert reg.entity_types() == ["tests.another", "tests.thing"]


def test_unknown_entity_type_is_a_422_not_a_key_error() -> None:
    with pytest.raises(ValidationFailedError, match="unknown entity type"):
        _registry().get("tests.nope")


def test_unknown_field_key_is_a_422() -> None:
    with pytest.raises(ValidationFailedError, match="unknown field"):
        _registry().get_field("tests.thing", "nope")


def test_registry_validates_clean_against_the_real_model() -> None:
    assert _registry().validate_against_models({"TenantThing": TenantThing}) == []


def test_registry_key_with_no_matching_column_is_a_boot_failure() -> None:
    """Silent drift would remove a field from every form, so boot fails."""
    reg = FieldRegistry()
    reg.register(
        EntityFields(
            entity_type="tests.thing",
            model_name="TenantThing",
            fields={"nonexistent_column": NativeField()},
        )
    )
    problems = reg.validate_against_models({"TenantThing": TenantThing})
    assert len(problems) == 1
    assert "no such column" in problems[0]


def test_missing_model_is_also_a_boot_failure() -> None:
    reg = _registry()
    problems = reg.validate_against_models({})
    assert problems and "no model named" in problems[0]


# --- field_config write-time guards ------------------------------------------


def _allow(reg: FieldRegistry, key: str, **kwargs: object) -> None:
    assert_config_allowed(
        reg.get_field("tests.thing", key),
        field_key=key,
        is_visible=kwargs.get("is_visible"),  # type: ignore[arg-type]
        is_required=kwargs.get("is_required"),  # type: ignore[arg-type]
        label_override=kwargs.get("label_override"),  # type: ignore[arg-type]
    )


def test_an_optional_field_may_be_hidden_relabelled_and_tightened() -> None:
    reg = _registry()
    _allow(reg, "qty", is_visible=False, is_required=True, label_override="Units")


def test_inheriting_config_is_allowed() -> None:
    """All three NULL means "inherit", which is the common row."""
    _allow(_registry(), "qty")


def test_a_non_hideable_field_cannot_be_hidden() -> None:
    reg = _registry()
    with pytest.raises(ValidationFailedError, match="cannot be hidden"):
        _allow(reg, "name", is_visible=False)


def test_a_money_driving_field_cannot_be_hidden() -> None:
    reg = _registry()
    with pytest.raises(ValidationFailedError) as exc:
        _allow(reg, "currency", is_visible=False)
    assert "drives money" in str(exc.value)


def test_requiredness_may_only_tighten() -> None:
    """Loosening switches off form enforcement of a NOT NULL column, and every
    create then 500s at the database instead of returning 422."""
    reg = _registry()
    with pytest.raises(ValidationFailedError, match="cannot be made optional"):
        _allow(reg, "name", is_required=False)


def test_making_an_optional_field_required_is_allowed() -> None:
    _allow(_registry(), "amount", is_required=True)


def test_a_statutory_field_cannot_be_relabelled() -> None:
    reg = _registry()
    with pytest.raises(ValidationFailedError, match="cannot be relabelled"):
        _allow(reg, "name", label_override="Trading name")


def test_showing_a_non_hideable_field_is_a_no_op_not_an_error() -> None:
    """``is_visible=True`` on a non-hideable field only restates the default."""
    _allow(_registry(), "name", is_visible=True)


def test_rejection_names_the_field_so_the_form_can_point_at_it() -> None:
    reg = _registry()
    with pytest.raises(ValidationFailedError) as exc:
        _allow(reg, "name", is_visible=False)
    assert exc.value.extra["fields"] == {"name": "not hideable"}


def test_requires_feature_is_recorded_on_the_registry_entry() -> None:
    """Resolution against company features happens in ``identity``; the registry
    only records the dependency."""
    assert _registry().get_field("tests.thing", "amount").requires_feature == "pricing"


def test_group_and_order_carry_the_default_layout() -> None:
    field = _registry().get_field("tests.thing", "qty")
    assert (field.group, field.order) == ("lines", 10)


def test_native_field_is_immutable() -> None:
    """Frozen so a request handler cannot mutate the shared code catalogue."""
    field = NativeField()
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
        field.required = True  # type: ignore[misc]
