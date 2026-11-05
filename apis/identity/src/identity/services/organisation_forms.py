"""Form descriptors derived from the existing, strict organization input schemas.

These entities have no registered field-policy/custom-field surface. Descriptors
describe their real API contracts, not new layout or authorization overrides.
"""

from typing import Any

from pydantic import BaseModel

from identity.schemas.company import FieldDescriptor, FieldSet


def form_fields(schema: type[BaseModel], entity: str, model: str, writable: bool) -> FieldSet:
    properties: dict[str, Any] = schema.model_json_schema()["properties"]
    fields = []
    for index, (key, prop) in enumerate(properties.items()):
        variants = prop.get("anyOf", [prop])
        scalar: dict[str, Any] = next((item for item in variants if item.get("type") != "null"), {})
        nullable = any(item.get("type") == "null" for item in variants)
        fields.append(
            FieldDescriptor(
                key=key,
                label=key.replace("_id", "").replace("_", " ").capitalize(),
                required=not nullable or key in getattr(schema, "nonnullable", frozenset()),
                hideable=False,
                renameable=False,
                requires_feature=None,
                group="identity",
                order=index * 10,
                writable=writable,
                data_type="reference" if scalar.get("format") == "uuid" else "string",
                validation={
                    "nullable": nullable,
                    **{
                        name: scalar[source]
                        for name, source in {
                            "min_length": "minLength",
                            "max_length": "maxLength",
                            "pattern": "pattern",
                        }.items()
                        if source in scalar
                    },
                },
            )
        )
    return FieldSet(entity_type=entity, model_name=model, fields=fields)
