import pytest
from billing_platform.errors import ValidationFailedError

from notification.domain.catalogue import (
    render_payload,
    validate_content,
    validate_schema,
    validate_variables,
)
from notification.domain.template import render

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": 12},
        "count": {"type": "integer"},
        "enabled": {"type": "boolean"},
        "number": {"type": "number"},
    },
    "required": ["name"],
    "additionalProperties": False,
}


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array"},
        {"type": "object", "properties": []},
        {"type": "object", "properties": {"a-b": {"type": "string"}}},
        {"type": "object", "required": [{}]},
        {"type": "object", "properties": {"x": {"type": []}}},
        {"type": "object", "properties": {"x": {"type": "string", "maxLength": True}}},
        {"type": "object", "properties": {"x": {"type": "string", "enum": []}}},
        {"type": "object", "additionalProperties": True},
    ],
)
def test_invalid_schema_is_a_validation_failure(schema):
    with pytest.raises(ValidationFailedError):
        validate_schema(schema)


@pytest.mark.parametrize(
    "variables",
    [
        {},
        {"name": "too long for schema"},
        {"name": "Ada", "extra": 1},
        {"name": "Ada", "count": True},
        {"name": "Ada", "enabled": "yes"},
        {"name": "Ada", "number": 1.5},
    ],
)
def test_invalid_template_values_are_rejected(variables):
    with pytest.raises(ValidationFailedError):
        validate_variables(SCHEMA, variables)


def test_typed_values_enum_and_render_boundaries():
    validate_variables(SCHEMA, {"name": "Ada", "count": 1, "enabled": True, "number": 2})
    enum_schema = {"type": "object", "properties": {"x": {"type": "string", "enum": ["a"]}}}
    with pytest.raises(ValidationFailedError):
        validate_variables(enum_schema, {"x": "b"})
    with pytest.raises(ValidationFailedError):
        render("{{ missing }}", {})
    with pytest.raises(ValidationFailedError):
        render("{{ name }}", {"name": "long"}, max_bytes=2)


def test_whatsapp_components_are_typed_ordered_and_frozen():
    components = [
        {"type": "header", "parameters": [{"type": "text", "variable": "name"}]},
        {
            "type": "body",
            "parameters": [
                {"type": "text", "variable": "count"},
                {"type": "text", "variable": "name"},
            ],
        },
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "variable": "name"}],
        },
    ]
    validate_content(SCHEMA, ["Hi {{ name }}"], {"components": components})
    payload = render_payload({"components": components}, {"name": "Ada", "count": 3})
    assert payload["components"][1]["parameters"] == [
        {"type": "text", "text": "3"},
        {"type": "text", "text": "Ada"},
    ]
    assert payload["components"][2]["sub_type"] == "url"
    assert render_payload(None, {}) == {}
    assert (
        render_payload({"template_parameters": ["name"]}, {"name": "Ada"})["components"][0]["type"]
        == "body"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": []},
        {"components": {}},
        {"components": [1]},
        {"components": [{"type": []}]},
        {"components": [{"type": "button", "sub_type": "quick_reply", "index": "0"}]},
        {"components": [{"type": "body", "index": "0"}]},
        {"components": [{"type": "header", "parameters": []}]},
        {"components": [{"type": "body", "parameters": [{"type": "image", "variable": "name"}]}]},
        {"components": [{"type": "body", "parameters": [{"type": "text", "variable": "missing"}]}]},
        {
            "components": [{"type": "body", "parameters": [{"type": "text", "variable": "name"}]}]
            * 2
        },
        {"template_parameters": ["name"], "components": [{"type": "body"}]},
    ],
)
def test_invalid_whatsapp_components_are_rejected(payload):
    with pytest.raises(ValidationFailedError):
        validate_content(SCHEMA, [], payload)
