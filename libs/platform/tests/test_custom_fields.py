from typing import Any

import pytest
from pydantic import ValidationError

from billing_platform.custom_fields import (
    Choice,
    CustomDefinition,
    ValidationRules,
    canonical_claim,
    condition_fields,
    condition_matches,
    safe_pattern,
    validate_definitions,
    validate_values,
)
from billing_platform.errors import PermissionDeniedError, ValidationFailedError


def definition(kind: str = "text", **kwargs: Any) -> CustomDefinition:
    return CustomDefinition.model_validate({"key": "cf_value", "data_type": kind, **kwargs})


def values(
    defs: tuple[CustomDefinition, ...], supplied: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "previous": {},
        "previous_native_values": {"item_type": "goods"},
        "native_values": {"item_type": "goods"},
        "creating": True,
        "readable_condition_fields": frozenset({"item_type", *(d.key for d in defs)}),
        "currencies": frozenset({"INR", "USD"}),
        "resolve_options": lambda source, parent: frozenset({"allowed"}),
    }
    return validate_values(defs, supplied, **{**options, **kwargs})


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("text", "hello", "hello"),
        ("long_text", "text", "text"),
        ("integer", 42, 42),
        ("decimal", "12.25", "12.2500"),
        ("boolean", True, True),
        ("date", "2026-01-01", "2026-01-01"),
        ("datetime", "2026-01-01T05:30:00+05:30", "2026-01-01T00:00:00+00:00"),
        (
            "currency_amount",
            {"amount": "1.25", "currency": "USD"},
            {"amount": "1.2500", "currency": "USD"},
        ),
    ],
)
def test_exact_scalar_storage(kind: str, value: Any, expected: Any) -> None:
    assert values((definition(kind),), {"cf_value": value}) == {"cf_value": expected}


@pytest.mark.parametrize(
    "kind,value",
    [
        ("integer", True),
        ("integer", 2**64),
        ("decimal", 1.25),
        ("decimal", "NaN"),
        ("boolean", 1),
        ("date", "2026-01-01T00:00:00Z"),
        ("date", "2026-02-30"),
        ("datetime", "2026-01-01"),
        ("datetime", 3),
        ("currency_amount", {"amount": "2", "currency": "BAD"}),
        ("text", "x" * 513),
        ("text", "\x00"),
    ],
)
def test_invalid_scalar_is_safe_error(kind: str, value: Any) -> None:
    with pytest.raises(ValidationFailedError):
        values((definition(kind),), {"cf_value": value})


def test_numeric_bounds_and_precision_and_text_pattern() -> None:
    number = definition(
        "decimal",
        validation=ValidationRules.model_validate({"min": "0", "max": "10", "decimal_places": 2}),
    )
    for value in ("-1", "11", "1.001"):
        with pytest.raises(ValidationFailedError):
            values((number,), {"cf_value": value})
    pattern = definition(
        validation=ValidationRules(regex=r"^[A-Z]{2}-\d{4}$", min_length=7, max_length=7)
    )
    assert values((pattern,), {"cf_value": "AB-1234"})["cf_value"] == "AB-1234"
    with pytest.raises(ValidationFailedError):
        values((pattern,), {"cf_value": "bad"})
    for regex in ["(a+)+$", "a|b", r"\1", "a{1,9}", "a{999}", "[", ""]:
        with pytest.raises(ValueError):
            safe_pattern(regex)
    for rules in [{"min_length": 10, "max_length": 1}, {"min": "2", "max": "1"}, {"min": 1.25}]:
        with pytest.raises(ValidationError):
            ValidationRules.model_validate(rules)


@pytest.mark.parametrize("amount", ["-1", "11"])
def test_currency_amount_honors_numeric_bounds(amount: str) -> None:
    field = definition(
        "currency_amount", validation=ValidationRules.model_validate({"min": "0", "max": "10"})
    )
    with pytest.raises(ValidationFailedError):
        values((field,), {"cf_value": {"amount": amount, "currency": "USD"}})


def test_selects_dynamic_source_and_inactive_history() -> None:
    choices = (Choice(value="a", label="A"), Choice(value="b", label="B", is_active=False))
    single = definition("select", choices=choices)
    multi = definition("multi_select", choices=choices)
    assert values((single,), {"cf_value": "a"})["cf_value"] == "a"
    assert values((multi,), {"cf_value": ["a"]})["cf_value"] == ["a"]
    for bad in [["b"], ["a", "a"], [1], "a"]:
        with pytest.raises(ValidationFailedError):
            values((multi,), {"cf_value": bad})
    assert values((single,), {}, previous={"cf_value": "b"}, creating=False)["cf_value"] == "b"
    dynamic = definition("dynamic_select", option_source_key="catalog.category")
    assert values((dynamic,), {"cf_value": "allowed"})["cf_value"] == "allowed"
    with pytest.raises(ValidationFailedError):
        values((dynamic,), {"cf_value": "unavailable"})


def test_definition_contract_and_graph_validation() -> None:
    cases: list[tuple[str, dict[str, Any]]] = [
        ("select", {}),
        ("dynamic_select", {}),
        ("long_text", {"is_searchable": True}),
        ("text", {"validation": ValidationRules(unique_within="company")}),
        (
            "multi_select",
            {
                "choices": (Choice(value="a", label="A"),),
                "is_searchable": True,
                "validation": ValidationRules(unique_within="company"),
            },
        ),
        ("select", {"choices": (Choice(value="a", label="A"), Choice(value="a", label="Again"))}),
    ]
    for kind, args in cases:
        with pytest.raises(ValidationError):
            definition(kind, **args)
    base = definition()
    validate_definitions(
        (base,), native_fields=frozenset({"item_type"}), option_sources=frozenset()
    )
    for defs in [
        (base, base),
        (definition("dynamic_select", option_source_key="https://bad"),),
        (definition(depends_on_key="unknown"),),
        (definition(visibility={"field": "cf_value", "cmp": "empty"}),),
    ]:
        with pytest.raises(ValidationFailedError):
            validate_definitions(defs, native_fields=frozenset(), option_sources=frozenset())
    first = CustomDefinition(key="cf_first", data_type="text", depends_on_key="cf_second")
    second = CustomDefinition(key="cf_second", data_type="text")
    validate_definitions((first, second), native_fields=frozenset(), option_sources=frozenset())


@pytest.mark.parametrize(
    "cmp,actual,expected,result",
    [
        ("eq", True, 1, False),
        ("ne", True, 1, True),
        ("in", "a", ["a"], True),
        ("not_in", "a", ["b"], True),
        ("gt", 2, 1, True),
        ("gte", 2, 2, True),
        ("lt", 1, 2, True),
        ("lte", 2, 2, True),
        ("empty", None, None, True),
        ("not_empty", [], None, False),
        ("matches", "AB", "[A-Z]{2}", True),
        ("gt", None, 1, False),
        ("gt", True, 0, False),
    ],
)
def test_condition_comparisons(cmp: str, actual: Any, expected: Any, result: bool) -> None:
    rule = {"field": "cf_value", "cmp": cmp, "value": expected}
    condition_fields(rule, allowed=frozenset({"cf_value"}))
    assert condition_matches(rule, {"cf_value": actual}) is result


def test_conditional_requiredness_defaults_order_and_denied_sources() -> None:
    child = CustomDefinition(
        key="cf_child",
        data_type="text",
        visibility={"field": "cf_parent", "cmp": "eq", "value": "yes"},
        validation=ValidationRules(required=True),
    )
    parent = CustomDefinition(key="cf_parent", data_type="text", default_value="yes")
    with pytest.raises(ValidationFailedError):
        values((child, parent), {})
    assert values((child, parent), {"cf_child": "present"})["cf_parent"] == "yes"
    with pytest.raises(PermissionDeniedError):
        values((child, parent), {"cf_child": "present"}, readable_condition_fields=frozenset())
    with pytest.raises(ValidationFailedError):
        values((child, parent), {"cf_parent": "no", "cf_child": "hidden"})
    number = CustomDefinition(key="cf_parent", data_type="decimal")
    child = child.model_copy(
        update={"visibility": {"field": "cf_parent", "cmp": "gt", "value": "2"}}
    )
    with pytest.raises(ValidationFailedError):
        values((child, number), {"cf_parent": "10"})


def test_readonly_unknown_inactive_and_null_values() -> None:
    with pytest.raises(ValidationFailedError):
        values((definition(),), {"cf_unknown": "x"})
    for d in (
        definition("auto_number", sequence_config={}),
        definition(is_active=False),
        definition(is_immutable_after_create=True),
    ):
        with pytest.raises(ValidationFailedError):
            values((d,), {"cf_value": "changed"}, creating=False, previous={"cf_value": "old"})
    assert values((definition(),), {"cf_value": None}) == {"cf_value": None}
    assert values((definition(is_active=False),), {}, previous={"cf_value": "kept"}) == {
        "cf_value": "kept"
    }
    assert values((definition("auto_number", sequence_config={}),), {}) == {}
    assert values((definition(default_value="fallback"),), {}) == {"cf_value": "fallback"}
    with pytest.raises(ValidationFailedError):
        values((definition("integer", default_value="bad"),), {})


def test_canonical_logical_claims_and_currency_identity() -> None:
    rules = ValidationRules(unique_within="company", case_sensitive=False)
    text = definition(is_searchable=True, validation=rules)
    assert canonical_claim(text, " A ") == canonical_claim(text, "a")
    assert canonical_claim(text, "") is None and canonical_claim(text, None) is None
    assert canonical_claim(definition(), "x") is None
    number = definition("decimal", is_searchable=True, validation=rules)
    assert canonical_claim(number, "1.0") == canonical_claim(number, "1.0000")
    amount = definition("currency_amount", is_searchable=True, validation=rules)
    assert canonical_claim(amount, {"currency": "INR", "amount": "1.0"}) != canonical_claim(
        amount, {"currency": "USD", "amount": "1.0"}
    )
    assert canonical_claim(amount, {"currency": "USD", "amount": "1.0"}) == canonical_claim(
        amount, {"currency": "USD", "amount": "1.0000"}
    )


def test_bounded_condition_groups_and_malformed_operands() -> None:
    rule = {"field": "cf_value", "cmp": "eq", "value": "yes"}
    for op, expected in [("and", True), ("or", True), ("not", False)]:
        group = {"op": op, "rules": [rule]}
        assert condition_fields(group, allowed=frozenset({"cf_value"})) == frozenset({"cf_value"})
        assert condition_matches(group, {"cf_value": "yes"}) is expected
    invalid: list[Any] = [
        None,
        {},
        {"op": "bad", "rules": [rule]},
        {"op": [], "rules": [rule]},
        {"op": "and", "rules": []},
        {"op": "not", "rules": [rule, rule]},
        {"field": [], "cmp": "empty"},
        {"field": "cf_value", "cmp": []},
        {"field": "cf_value", "cmp": "eq"},
        {"field": "cf_value", "cmp": "in", "value": "bad"},
        {"field": "cf_value", "cmp": "matches", "value": 2},
        {"field": "cf_value", "cmp": "matches", "value": "(a+)+"},
    ]
    deep: Any = rule
    for _ in range(8):
        deep = {"op": "and", "rules": [deep]}
    wide = {"op": "and", "rules": [{"op": "or", "rules": [rule] * 16}] * 16}
    invalid.extend([deep, wide])
    for tree in invalid:
        with pytest.raises(ValidationFailedError):
            condition_fields(tree, allowed=frozenset({"cf_value"}))
    for value in [None, True, "NaN"]:
        assert not condition_matches(
            {"field": "cf_value", "cmp": "gt", "value": "2"},
            {"cf_value": value},
            numeric_fields=frozenset({"cf_value"}),
        )
    assert not condition_matches({"field": "cf_value", "cmp": "gt", "value": {}}, {"cf_value": {}})


def test_dynamic_parent_policy_and_present_defaults() -> None:
    dynamic = definition(
        "dynamic_select", option_source_key="catalog.category", depends_on_key="item_type"
    )
    with pytest.raises(PermissionDeniedError):
        values((dynamic,), {"cf_value": "allowed"}, readable_condition_fields=frozenset())
    validate_definitions(
        (dynamic,),
        native_fields=frozenset({"item_type"}),
        option_sources=frozenset({"catalog.category"}),
    )
    assert (
        values((definition(default_value="fallback"),), {"cf_value": "given"})["cf_value"]
        == "given"
    )
    hidden = definition(
        visibility={"field": "item_type", "cmp": "eq", "value": "service"},
        validation=ValidationRules(required=True),
    )
    assert values((hidden,), {}) == {}


def test_decimal_immutable_comparison_is_semantic() -> None:
    immutable = definition("decimal", is_immutable_after_create=True)
    assert (
        values((immutable,), {"cf_value": "1.0"}, previous={"cf_value": "1.0000"}, creating=False)[
            "cf_value"
        ]
        == "1.0000"
    )


def test_cascading_parent_change_revalidates_retained_child() -> None:
    child = definition(
        "dynamic_select", option_source_key="catalog.category", depends_on_key="cf_parent"
    )
    parent = CustomDefinition(key="cf_parent", data_type="text")
    with pytest.raises(ValidationFailedError):
        values(
            (parent, child),
            {"cf_parent": "new"},
            previous={"cf_parent": "old", "cf_value": "old-child"},
            creating=False,
        )


def test_option_identity_fixed_patterns_and_unsupported_kind() -> None:
    for option in ["a ", " a", "a\n"]:
        with pytest.raises(ValidationError):
            Choice(value=option, label="invalid")
    pattern = definition(validation=ValidationRules(regex=r"^[A-Z]{2}-\d{4}$"))
    with pytest.raises(ValidationFailedError):
        values((pattern,), {"cf_value": "AB-000A"})
    with pytest.raises(ValidationFailedError):
        values(
            (definition().model_copy(update={"data_type": "future-unsupported"}),),
            {"cf_value": "x"},
        )
    case = definition(is_searchable=True, validation=ValidationRules(unique_within="company"))
    assert canonical_claim(case, "A") != canonical_claim(case, "a")


def test_auto_number_requires_explicit_typed_sequence_configuration() -> None:
    from billing_platform.custom_fields import SequenceRules

    assert definition("auto_number", sequence_config={}).sequence_config == SequenceRules()
    assert SequenceRules(prefix="IT-").prefix == "IT-"
    for kind, config in [
        ("auto_number", None),
        ("text", {}),
        ("auto_number", {"reset": "unsafe"}),
        ("auto_number", {"prefix": "\n"}),
    ]:
        with pytest.raises(ValidationError):
            definition(kind, sequence_config=config)
    with pytest.raises(ValidationError):
        definition("auto_number", sequence_config={}, default_value="injected")


@pytest.mark.parametrize("value,message", [("bad", "Use uppercase"), (42, "invalid value")])
def test_pattern_message_is_only_used_for_a_pattern_failure(value: Any, message: str) -> None:
    field = definition(validation={"regex": "[A-Z]{3}", "regex_message": "Use uppercase"})
    with pytest.raises(ValidationFailedError) as error:
        values((field,), {"cf_value": value})
    assert error.value.extra["fields"] == {"cf_value": message}
