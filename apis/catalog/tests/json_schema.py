"""A strict, dependency-free JSON Schema subset validator for contract tests.

``jsonschema`` is not a Catalog dependency and a test helper does not justify one (CLAUDE.md
§5.15). This validator implements exactly the keywords Accounting's published contracts use
and *fails on any keyword it does not know*, so a contract that grows a new constraint breaks
this test instead of being silently half-checked.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

CONTRACTS = Path(__file__).resolve().parents[2] / "accounting" / "contracts"
ANNOTATIONS = frozenset({"title", "description", "default", "$defs"})
KNOWN = ANNOTATIONS | {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "const",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "format",
    "anyOf",
    "$ref",
    "items",
    "minItems",
    "maxItems",
    # Pydantic's decimal extensions on string-typed decimals.
    "decimal_places",
    "max_digits",
    "gt",
}
TYPES: dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def load(name: str) -> dict[str, Any]:
    value = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def errors(schema: dict[str, Any], value: Any) -> list[str]:
    found: list[str] = []
    _check(schema, schema, value, "$", found)
    return found


def _type(expected: str, value: Any) -> bool:
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float)
    return type(value) is TYPES[expected]


def _decimal(value: str) -> Decimal | None:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _check(
    root: dict[str, Any], schema: dict[str, Any], value: Any, path: str, out: list[str]
) -> None:
    unknown = set(schema) - KNOWN
    if unknown:
        raise AssertionError(f"unsupported JSON Schema keywords at {path}: {sorted(unknown)}")
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/$defs/"), ref
        _check(root, root["$defs"][ref.removeprefix("#/$defs/")], value, path, out)
    if "anyOf" in schema:
        if not any(not errors_for(root, option, value, path) for option in schema["anyOf"]):
            out.append(f"{path}: matches no anyOf branch")
    if "type" in schema and not _type(schema["type"], value):
        out.append(f"{path}: expected {schema['type']}, got {type(value).__name__}")
        return
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        out.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in enum")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(f"{path}: longer than {schema['maxLength']}")
        if schema.get("format") == "uuid":
            try:
                if str(uuid.UUID(value)) != value:
                    out.append(f"{path}: non-canonical uuid")
            except ValueError:
                out.append(f"{path}: not a uuid")
        elif schema.get("format") == "date":
            try:
                dt.date.fromisoformat(value)
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError(value)
            except ValueError:
                out.append(f"{path}: not an ISO date")
        elif "format" in schema:
            raise AssertionError(f"unsupported format {schema['format']} at {path}")
        if {"decimal_places", "max_digits", "gt"} & set(schema):
            number = _decimal(value)
            if number is None:
                out.append(f"{path}: not a decimal string")
            else:
                exponent = number.as_tuple().exponent
                assert isinstance(exponent, int)
                places = max(0, -exponent)
                if "decimal_places" in schema and places > schema["decimal_places"]:
                    out.append(f"{path}: more than {schema['decimal_places']} places")
                if "max_digits" in schema and len(number.as_tuple().digits) > schema["max_digits"]:
                    out.append(f"{path}: more than {schema['max_digits']} digits")
                if "gt" in schema and not number > Decimal(str(schema["gt"])):
                    out.append(f"{path}: not greater than {schema['gt']}")
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: above {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, entry in enumerate(value):
                _check(root, schema["items"], entry, f"{path}[{index}]", out)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}: missing {key}")
        if schema.get("additionalProperties") is False:
            for key in set(value) - set(properties):
                out.append(f"{path}: unexpected {key}")
        elif "additionalProperties" in schema:
            raise AssertionError(f"unsupported additionalProperties at {path}")
        for key, sub in properties.items():
            if key in value:
                _check(root, sub, value[key], f"{path}.{key}", out)


def errors_for(root: dict[str, Any], schema: dict[str, Any], value: Any, path: str) -> list[str]:
    found: list[str] = []
    _check(root, schema, value, path, found)
    return found


def assert_valid(schema: dict[str, Any], value: Any) -> None:
    problems = errors(schema, value)
    assert not problems, problems
