"""Bounded custom-value validation and canonical indexing contracts.

No business-domain decisions or I/O. Definitions come from authenticated local
projections. Dynamic options and auto-number allocation are explicit callbacks;
there is no URL/query execution or fallback to a missing source.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.idempotency import canonical_json

MAX_DEFINITIONS = 128
MAX_TEXT = 4096


class ValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    required: StrictBool = False
    min: Decimal | None = None
    max: Decimal | None = None
    min_length: int = Field(default=0, strict=True, ge=0, le=MAX_TEXT)
    max_length: int = Field(default=MAX_TEXT, strict=True, ge=1, le=MAX_TEXT)
    decimal_places: int = Field(default=4, strict=True, ge=0, le=4)
    regex: str | None = Field(default=None, max_length=256)
    regex_message: str | None = Field(default=None, min_length=1, max_length=200)
    unique_within: Literal["none", "company", "tenant"] = "none"
    case_sensitive: StrictBool = True

    @field_validator("min", "max", mode="before")
    @classmethod
    def exact_bounds(cls, value: Any) -> Decimal | None:
        return None if value is None else exact_decimal(value)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.min_length > self.max_length or (
            self.min is not None and self.max is not None and self.min > self.max
        ):
            raise ValueError("invalid validation bounds")
        if self.regex is not None:
            safe_pattern(self.regex)
        return self


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    is_active: StrictBool = True

    @field_validator("value")
    @classmethod
    def stable_option_identity(cls, value: str) -> str:
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("option identifiers cannot contain surrounding whitespace or controls")
        return value


class SequenceRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prefix: str = Field(default="", max_length=64)
    padding: int = Field(default=1, strict=True, ge=1, le=20)
    start: int = Field(default=1, strict=True, ge=1, lt=2**63 - 1)
    reset: Literal["never", "calendar_year", "month", "fiscal_year"] = "never"

    @field_validator("prefix")
    @classmethod
    def safe_prefix(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("sequence prefix cannot contain controls")
        return value


class CustomDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(pattern=r"^cf_[a-z][a-z0-9_]{0,59}$")
    data_type: Literal[
        "text",
        "long_text",
        "integer",
        "decimal",
        "boolean",
        "date",
        "datetime",
        "currency_amount",
        "select",
        "multi_select",
        "dynamic_select",
        "auto_number",
    ]
    is_active: StrictBool = True
    is_searchable: StrictBool = False
    is_immutable_after_create: StrictBool = False
    validation: ValidationRules = Field(default_factory=ValidationRules)
    choices: tuple[Choice, ...] = Field(default=(), max_length=200)
    option_source_key: str | None = Field(default=None, max_length=100)
    depends_on_key: str | None = Field(default=None, max_length=64)
    visibility: dict[str, Any] | None = None
    default_value: Any = None
    sequence_config: SequenceRules | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.data_type == "auto_number") != (self.sequence_config is not None):
            raise ValueError("auto-number requires explicit sequence configuration only")
        if self.data_type == "auto_number" and self.default_value is not None:
            raise ValueError("auto-number cannot have an authored default value")
        if len({choice.value for choice in self.choices}) != len(self.choices):
            raise ValueError("duplicate option identities")
        if self.data_type in {"select", "multi_select"} and not self.choices:
            raise ValueError("static select requires choices")
        if self.data_type == "dynamic_select" and not self.option_source_key:
            raise ValueError("dynamic select requires a registered source")
        if self.validation.unique_within != "none":
            if not self.is_searchable or self.data_type in {"multi_select", "long_text"}:
                raise ValueError("uniqueness requires a supported searchable scalar")
        if self.is_searchable and self.data_type == "long_text":
            raise ValueError("long text is not an indexed scalar")
        return self


def safe_pattern(pattern: str) -> re.Pattern[str]:
    """Linear subset: literals/classes/anchors and fixed repetitions only.

    Reject backreferences, branching, groups and variable repetition. This is a
    documented initial subset, not an unrestricted Python regular expression.
    """
    if not pattern or len(pattern) > 256 or re.search(r"[()|+*?]", pattern):
        raise ValueError("unsupported regular expression")
    if re.search(r"\\(?![dDsSwW\\.\[\]{}^$-])", pattern):
        raise ValueError("unsupported regular expression escape")
    stripped = re.sub(r"\{([0-9]{1,3})\}", "", pattern)
    if "{" in stripped or "}" in stripped:
        raise ValueError("only fixed bounded repetition is supported")
    if any(int(n) > 256 for n in re.findall(r"\{([0-9]+)\}", pattern)):
        raise ValueError("regular expression repetition exceeds bound")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError("invalid regular expression") from exc


def condition_fields(
    tree: dict[str, Any],
    *,
    allowed: frozenset[str],
    depth: int = 0,
    _budget: list[int] | None = None,
) -> frozenset[str]:
    budget = [128] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0 or depth > 6 or not isinstance(tree, dict):
        raise ValidationFailedError("condition tree exceeds its bounds")
    if "op" in tree:
        rules = tree.get("rules")
        if (
            set(tree) != {"op", "rules"}
            or not isinstance(tree["op"], str)
            or tree["op"] not in {"and", "or", "not"}
            or not isinstance(rules, list)
            or not 1 <= len(rules) <= 16
            or (tree["op"] == "not" and len(rules) != 1)
        ):
            raise ValidationFailedError("unsupported condition group")
        return frozenset().union(
            *(
                condition_fields(rule, allowed=allowed, depth=depth + 1, _budget=budget)
                for rule in rules
            )
        )
    cmp = tree.get("cmp")
    if (
        set(tree) - {"field", "cmp", "value"}
        or not isinstance(tree.get("field"), str)
        or tree.get("field") not in allowed
        or not isinstance(cmp, str)
        or cmp
        not in {
            "eq",
            "ne",
            "in",
            "not_in",
            "gt",
            "gte",
            "lt",
            "lte",
            "empty",
            "not_empty",
            "matches",
        }
    ):
        raise ValidationFailedError("unsupported condition predicate")
    if cmp not in {"empty", "not_empty"} and "value" not in tree:
        raise ValidationFailedError("condition operand required")
    if cmp in {"in", "not_in"} and (
        not isinstance(tree["value"], list) or len(tree["value"]) > 100
    ):
        raise ValidationFailedError("condition membership is not bounded")
    if cmp == "matches":
        if not isinstance(tree["value"], str):
            raise ValidationFailedError("condition pattern must be text")
        try:
            safe_pattern(tree["value"])
        except ValueError as exc:
            raise ValidationFailedError("unsupported condition pattern") from exc
    return frozenset({tree["field"]})


def decode_default(kind: str, value: str | None) -> Any:
    """Read JSON-encoded defaults and legacy unquoted scalar defaults.

    Decimal values remain text. Booleans, arrays and objects always use JSON;
    numeric JSON amounts are rejected rather than passed through a float.
    """
    if value is None:
        return None

    def no_float(raw: str) -> None:
        raise ValueError("custom numeric defaults must use decimal strings")

    if kind in {"boolean", "multi_select", "currency_amount", "integer"} or value.startswith('"'):
        return json.loads(value, parse_float=no_float, parse_constant=no_float)
    return value


def _condition_operand(value: Any, actual: Any, *, numeric: bool) -> Any:
    if value is None:
        return None
    if numeric:
        if isinstance(value, bool) or not isinstance(value, int | str | Decimal):
            raise ValueError("numeric condition operand required")
        if len(str(value)) > 128:
            raise ValueError("condition operand exceeds bounds")
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("finite condition operand required")
        return number
    if isinstance(actual, uuid.UUID):
        return uuid.UUID(str(value))
    if isinstance(actual, dt.datetime):
        return value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
    if isinstance(actual, dt.date):
        return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)
    return value


def condition_matches(
    tree: dict[str, Any], values: Mapping[str, Any], *, numeric_fields: frozenset[str] = frozenset()
) -> bool:
    if "op" in tree:
        results = [
            condition_matches(rule, values, numeric_fields=numeric_fields) for rule in tree["rules"]
        ]
        return (
            all(results)
            if tree["op"] == "and"
            else any(results)
            if tree["op"] == "or"
            else not results[0]
        )
    actual, expected, cmp = values.get(tree["field"]), tree.get("value"), tree["cmp"]
    if cmp in {"empty", "not_empty"}:
        empty = actual is None or actual == "" or actual == []
        return empty if cmp == "empty" else not empty
    numeric = tree["field"] in numeric_fields or type(actual) in {int, Decimal}
    if cmp != "matches":
        try:
            reference = actual
            actual = _condition_operand(actual, reference, numeric=numeric)
            if cmp in {"in", "not_in"}:
                if not isinstance(expected, list):
                    return False
                expected = [
                    _condition_operand(value, reference, numeric=numeric) for value in expected
                ]
            else:
                expected = _condition_operand(expected, reference, numeric=numeric)
        except (ValueError, TypeError, InvalidOperation):
            return False
    if cmp == "eq":
        return type(actual) is type(expected) and actual == expected
    if cmp == "ne":
        return not (type(actual) is type(expected) and actual == expected)
    if cmp in {"in", "not_in"}:
        assert isinstance(expected, list)
        found = any(type(actual) is type(value) and actual == value for value in expected)
        return found if cmp == "in" else not found
    if cmp == "matches":
        assert isinstance(expected, str)
        return (
            isinstance(actual, str)
            and len(actual) <= MAX_TEXT
            and safe_pattern(expected).fullmatch(actual) is not None
        )
    if actual is None or type(actual) is not type(expected) or isinstance(actual, bool):
        return False
    try:
        return bool(
            {
                "gt": lambda: actual > expected,
                "gte": lambda: actual >= expected,
                "lt": lambda: actual < expected,
                "lte": lambda: actual <= expected,
            }[cmp]()
        )
    except TypeError:
        return False


def validate_definitions(
    definitions: tuple[CustomDefinition, ...],
    *,
    native_fields: frozenset[str],
    option_sources: frozenset[str],
) -> None:
    if len(definitions) > MAX_DEFINITIONS or len({d.key for d in definitions}) != len(definitions):
        raise ValidationFailedError("custom field count or logical identity is invalid")
    keys = frozenset(d.key for d in definitions)
    edges: dict[str, frozenset[str]] = {}
    for definition in definitions:
        if (
            definition.option_source_key is not None
            and definition.option_source_key not in option_sources
        ):
            raise ValidationFailedError("unregistered custom option source")
        refs = (
            condition_fields(definition.visibility, allowed=keys | native_fields)
            if definition.visibility is not None
            else frozenset()
        )
        if definition.depends_on_key is not None:
            if definition.depends_on_key not in keys | native_fields:
                raise ValidationFailedError("unknown cascading parent")
            refs |= {definition.depends_on_key}
        edges[definition.key] = refs & keys
    visited: set[str] = set()
    active: set[str] = set()

    def walk(key: str) -> None:
        if key in active:
            raise ValidationFailedError("custom field condition cycle")
        if key in visited:
            return
        active.add(key)
        for other in edges[key]:
            walk(other)
        active.remove(key)
        visited.add(key)

    for key in edges:
        walk(key)


class _PatternMismatchError(ValueError):
    """A bounded text pattern failed; other scalar errors use their own message."""


def scalar_value(definition: CustomDefinition, value: Any, *, currencies: frozenset[str]) -> Any:
    kind, rules = definition.data_type, definition.validation
    if kind in {"text", "long_text", "select", "dynamic_select", "auto_number"}:
        if (
            not isinstance(value, str)
            or not rules.min_length <= len(value) <= rules.max_length
            or "\x00" in value
        ):
            raise ValueError("invalid text")
        if kind != "long_text" and len(value) > 512:
            raise ValueError("scalar text exceeds bound")
        if rules.regex is not None and safe_pattern(rules.regex).fullmatch(value) is None:
            raise _PatternMismatchError("text does not match validation")
        return value
    if kind in {"integer", "decimal"}:
        if kind == "integer" and (type(value) is not int or not -(2**63) <= value < 2**63):
            raise ValueError("integer required")
        number = exact_decimal(
            value, decimal_places=0 if kind == "integer" else rules.decimal_places
        )
        if (rules.min is not None and number < rules.min) or (
            rules.max is not None and number > rules.max
        ):
            raise ValueError("number is outside bounds")
        return int(number) if kind == "integer" else format(number, "f")
    if kind == "boolean":
        if type(value) is not bool:
            raise ValueError("boolean required")
        return value
    if kind in {"date", "datetime"}:
        if not isinstance(value, str):
            raise ValueError("ISO date/time text required")
        if kind == "date":
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError("business date required")
            return dt.date.fromisoformat(value).isoformat()
        stamp = dt.datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            raise ValueError("timestamp requires an offset")
        return stamp.astimezone(dt.UTC).isoformat()
    if kind == "currency_amount":
        if (
            not isinstance(value, dict)
            or set(value) != {"amount", "currency"}
            or value["currency"] not in currencies
        ):
            raise ValueError("amount and supported currency required")
        amount = exact_decimal(value["amount"], decimal_places=rules.decimal_places)
        if (rules.min is not None and amount < rules.min) or (
            rules.max is not None and amount > rules.max
        ):
            raise ValueError("amount is outside its bounds")
        return {
            "amount": format(amount, "f"),
            "currency": value["currency"],
        }
    if kind == "multi_select":
        if (
            not isinstance(value, list)
            or len(value) > 100
            or any(not isinstance(v, str) for v in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError("distinct bounded option values required")
        return sorted(value)
    raise ValueError("unsupported custom type")


def validate_values(
    definitions: tuple[CustomDefinition, ...],
    supplied: Mapping[str, Any],
    *,
    previous: Mapping[str, Any],
    native_values: Mapping[str, Any],
    previous_native_values: Mapping[str, Any],
    creating: bool,
    readable_condition_fields: frozenset[str],
    currencies: frozenset[str],
    resolve_options: Callable[[str, Any], frozenset[str]],
) -> dict[str, Any]:
    by_key = {d.key: d for d in definitions}
    if set(supplied) - set(by_key):
        raise ValidationFailedError("unregistered custom field")
    result = dict(previous)
    for key, value in supplied.items():
        definition = by_key[key]
        if definition.data_type == "auto_number":
            raise ValidationFailedError("auto-number fields are read-only")
        if not definition.is_active and value != previous.get(key):
            raise ValidationFailedError("inactive custom field cannot change")
        if not definition.is_active:
            continue
        try:
            result[key] = (
                None if value is None else scalar_value(definition, value, currencies=currencies)
            )
        except (ValueError, TypeError, ValidationFailedError) as exc:
            raise ValidationFailedError(
                "invalid custom field value",
                fields={
                    key: definition.validation.regex_message
                    if isinstance(exc, _PatternMismatchError)
                    and definition.validation.regex_message
                    else "invalid value"
                },
            ) from exc
        if (
            not creating
            and definition.is_immutable_after_create
            and result[key] != previous.get(key)
        ):
            raise ValidationFailedError("custom field is immutable")
    for definition in definitions:
        key = definition.key
        if not definition.is_active or definition.data_type == "auto_number":
            continue
        if creating and key not in result and definition.default_value is not None:
            try:
                result[key] = scalar_value(
                    definition, definition.default_value, currencies=currencies
                )
            except (ValueError, TypeError, ValidationFailedError) as exc:
                raise ValidationFailedError("invalid custom field default") from exc
    for definition in definitions:
        key = definition.key
        if not definition.is_active or definition.data_type == "auto_number":
            continue
        visible = field_visible(
            definition, definitions, result, native_values, readable_condition_fields
        )
        if not visible:
            if key in supplied:
                raise ValidationFailedError("conditionally hidden custom field was supplied")
            continue
        value = result.get(key)
        if definition.validation.required and (value is None or value == "" or value == []):
            raise ValidationFailedError(
                "required custom field is missing", fields={key: "required"}
            )
        parent = definition.depends_on_key
        parent_changed = parent is not None and (
            result.get(parent) != previous.get(parent)
            or native_values.get(parent) != previous_native_values.get(parent)
        )
        if value is None or (
            not creating
            and not parent_changed
            and (key not in supplied or value == previous.get(key))
        ):
            continue
        allowed = frozenset(choice.value for choice in definition.choices if choice.is_active)
        if definition.data_type == "dynamic_select":
            assert definition.option_source_key is not None
            allowed = resolve_options(
                definition.option_source_key,
                {**native_values, **result}.get(definition.depends_on_key)
                if definition.depends_on_key is not None
                else None,
            )
        if definition.data_type in {"select", "dynamic_select", "multi_select"}:
            values = set(value) if definition.data_type == "multi_select" else {value}
            if not values <= allowed:
                raise ValidationFailedError(
                    "custom option is unavailable", fields={key: "unavailable option"}
                )
    return result


def field_visible(
    definition: CustomDefinition,
    definitions: tuple[CustomDefinition, ...],
    values: Mapping[str, Any],
    native_values: Mapping[str, Any],
    readable_fields: frozenset[str],
) -> bool:
    """One visibility contract for entry, stored-value validation and backfills."""
    if definition.depends_on_key is not None and definition.depends_on_key not in readable_fields:
        raise PermissionDeniedError("custom option source uses an unreadable parent")
    if definition.visibility is None:
        return True
    refs = condition_fields(
        definition.visibility,
        allowed=frozenset(d.key for d in definitions) | frozenset(native_values),
    )
    if not refs <= readable_fields:
        raise PermissionDeniedError("custom field condition uses an unreadable field")
    return condition_matches(
        definition.visibility,
        {**native_values, **values},
        numeric_fields=frozenset(
            d.key for d in definitions if d.data_type in {"decimal", "integer"}
        ),
    )


def validate_stored_values(
    definitions: tuple[CustomDefinition, ...],
    *,
    values: Mapping[str, Any],
    native_values: Mapping[str, Any],
    readable_fields: frozenset[str],
    currencies: frozenset[str],
    keys: frozenset[str] | None = None,
) -> None:
    """Check a stored contract without defaults, allocations or value mutations.

    Historical inactive choices remain valid. Changes select only active choices
    through validate_values; stored native dynamic references remain descriptive.
    """
    for definition in definitions:
        key = definition.key
        if not definition.is_active or (keys is not None and key not in keys):
            continue
        if key not in readable_fields:
            raise PermissionDeniedError("custom value validation requires readable fields")
        if not field_visible(definition, definitions, values, native_values, readable_fields):
            continue
        value = values.get(key)
        if (
            definition.data_type != "auto_number"
            and definition.validation.required
            and (value is None or value == "" or value == [])
        ):
            raise ValidationFailedError(
                "required custom field is missing", fields={key: "required"}
            )
        if value is not None:
            try:
                scalar_value(definition, value, currencies=currencies)
            except (ValueError, TypeError) as exc:
                raise ValidationFailedError(
                    "invalid custom field value", fields={key: "invalid value"}
                ) from exc
            if definition.data_type in {"select", "multi_select"}:
                selected = set(value) if definition.data_type == "multi_select" else {value}
                if not selected <= {choice.value for choice in definition.choices}:
                    raise ValidationFailedError(
                        "unknown custom option", fields={key: "unavailable option"}
                    )


def canonical_claim(definition: CustomDefinition, value: Any) -> tuple[bytes, bytes] | None:
    if value is None or value == "":
        return None
    if definition.validation.unique_within == "none":
        return None
    if isinstance(value, str):
        if definition.data_type == "decimal":
            value = format(Decimal(value).normalize(), "f")
        else:
            value = unicodedata.normalize("NFKC", value).strip()
            if not definition.validation.case_sensitive:
                value = value.casefold()
    if definition.data_type == "currency_amount":
        value = {**value, "amount": format(Decimal(value["amount"]).normalize(), "f")}
    content = canonical_json({"type": definition.data_type, "value": value})
    return hashlib.sha256(content).digest(), content
