"""Catalog's versioned product contract; no dependency on Catalog ORM models."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from billing_platform.custom_fields import CustomDefinition
from billing_platform.errors import ValidationFailedError
from billing_platform.fields import NativeField


@lru_cache(maxsize=1)
def contracts() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (Path(__file__).resolve().parents[1] / "data/catalog_fields.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def contract(entity: str) -> dict[str, Any]:
    value = contracts().get(entity)
    if value is None:
        raise ValidationFailedError("product field contract is not supported")
    return cast(dict[str, Any], value)


def native_field(entity: str, key: str) -> NativeField:
    value = contract(entity)["forms"].get(key)
    if value is None:
        raise ValidationFailedError("product layout field is not registered")
    return NativeField(**value)


def validate_options(entity: str, definitions: tuple[CustomDefinition, ...]) -> None:
    sources = contract(entity)["option_sources"]
    by_key = {d.key: d for d in definitions}
    for definition in definitions:
        if definition.option_source_key is None:
            continue
        source = sources[definition.option_source_key]
        parent = by_key.get(definition.depends_on_key or "")
        expected = source["parent_source"]
        if (expected is None) != (definition.depends_on_key is None) or (
            expected is not None and (parent is None or parent.option_source_key != expected)
        ):
            raise ValidationFailedError("option source requires its registered parent field")
