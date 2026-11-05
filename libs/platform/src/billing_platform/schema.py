"""Self-contained field definitions for clients that receive one field at a time."""

from typing import Any

from pydantic import BaseModel


def resolved_schema(model: type[BaseModel]) -> dict[str, Any]:
    document = model.model_json_schema()
    definitions = document.get("$defs", {})

    def resolve(value: Any, seen: frozenset[str] = frozenset()) -> Any:
        if isinstance(value, list):
            return [resolve(item, seen) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            name = value["$ref"].removeprefix("#/$defs/")
            if name not in definitions or name in seen:
                raise ValueError("field metadata requires an acyclic local schema reference")
            return resolve(
                definitions[name] | {key: item for key, item in value.items() if key != "$ref"},
                seen | {name},
            )
        return {key: resolve(item, seen) for key, item in value.items() if key != "$defs"}

    result: dict[str, Any] = resolve(document)
    return result
