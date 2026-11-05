"""Standalone schemas cannot leave broken references for field/HTTP consumers."""
import json

import pytest
from pydantic import BaseModel

from billing_platform.schema import resolved_schema


def test_nested_schema_retains_shape_without_external_definitions() -> None:
    class Line(BaseModel):
        amount: str
    class Document(BaseModel):
        lines: list[Line]
        optional: Line | None = None
    schema = resolved_schema(Document)
    assert "#/$defs/" not in json.dumps(schema)
    assert schema["properties"]["lines"]["items"]["required"] == ["amount"]
    assert schema["properties"]["optional"]["anyOf"][1] == {"type": "null"}


def test_recursive_schema_is_rejected() -> None:
    class Node(BaseModel):
        child: "Node | None" = None
    with pytest.raises(ValueError, match="acyclic"):
        resolved_schema(Node)
