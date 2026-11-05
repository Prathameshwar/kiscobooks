"""Shared response/request schema primitives.

Every schema forbids unknown fields (CLAUDE.md §5.6: no mass assignment, no silently
ignored input) and reads from ORM attributes so a route can return the model row and
let the ``response_model`` project it to the lean shape.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


def clean_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("enter text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("enter valid text without control characters")
    value = value.strip()
    if not value:
        raise ValueError("enter valid text without control characters")
    return value


def looks_like_email(value: str) -> str:
    """A light structural check and normalisation, shared by every schema with an email.

    Not full RFC validation (that needs a dependency and still accepts undeliverable
    addresses): it rejects the obviously-wrong and lower-cases so uniqueness is stable.
    """
    if "@" not in value or "." not in value.split("@")[-1]:
        raise ValueError("not a valid email address")
    return value.lower()


def nonnullable_schema(schema: dict[str, Any], model: type[BaseModel]) -> None:
    for key in getattr(model, "nonnullable", ()):
        field = schema.get("properties", {}).get(key, {})
        variants = [item for item in field.get("anyOf", []) if item.get("type") != "null"]
        if variants:
            field.pop("anyOf")
            field.update(variants[0] if len(variants) == 1 else {"anyOf": variants})
        if field.get("default") is None:
            field.pop("default", None)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, json_schema_extra=nonnullable_schema
    )
    nonnullable: ClassVar[frozenset[str]] = frozenset()

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def reject_required_nulls(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None and info.field_name in cls.nonnullable:
            raise ValueError("field cannot be null")
        return value


class PageMeta(StrictModel):
    """The cursor envelope returned alongside every list ``items`` array.

    No total by default (api-conventions §list): an unconditional exact count on a
    growing table is the query that quietly gets expensive.
    """

    next_cursor: str | None
    has_more: bool


class Page[T](StrictModel):
    items: list[T]
    page: PageMeta
