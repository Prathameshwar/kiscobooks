"""The native field registry — a code catalogue, no table.

``field_config`` rows override entries in this registry. There is deliberately no
``field`` table: native fields are model columns, a table would let an admin
invent one, and nothing could be statically checked.

Boot asserts every registry key resolves to a real column on the entity's model,
and that every ``field_config`` row points at a registered key. Silent drift
would remove a field from every form.
See docs/identity-schema.md §6.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from billing_platform.errors import ValidationFailedError


@dataclass(frozen=True, slots=True)
class NativeField:
    """One native column, and what a tenant admin may do to it."""

    #: Domain/DB requiredness. A floor: config may tighten, never loosen.
    required: bool = False
    #: May a tenant hide it from forms. False for anything NOT NULL, anything
    #: immutable after posting, anything printing on statutory output, and
    #: anything driving money.
    hideable: bool = True
    #: May a tenant override the label. False where the field appears in
    #: statutory output under its legal name.
    renameable: bool = True
    #: Resolves out of the effective set when this company feature is off.
    requires_feature: str | None = None
    #: Default form section and position.
    group: str = "general"
    order: int = 0
    #: Why it is not hideable. Required when ``hideable`` is False, so the
    #: rejection message can explain itself.
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.hideable and not self.reason:
            raise ValueError("a non-hideable field must state a reason")


@dataclass(frozen=True, slots=True)
class EntityFields:
    """The registered native fields of one entity type."""

    entity_type: str
    model_name: str
    fields: dict[str, NativeField] = field(default_factory=dict)


class FieldRegistry:
    """Registry of native fields per entity type."""

    def __init__(self) -> None:
        self._entities: dict[str, EntityFields] = {}

    def register(self, entity: EntityFields) -> None:
        if entity.entity_type in self._entities:
            raise ValueError(f"entity already registered: {entity.entity_type}")
        self._entities[entity.entity_type] = entity

    def entity_types(self) -> list[str]:
        return sorted(self._entities)

    def get(self, entity_type: str) -> EntityFields:
        try:
            return self._entities[entity_type]
        except KeyError:
            raise ValidationFailedError(f"unknown entity type: {entity_type}") from None

    def get_field(self, entity_type: str, field_key: str) -> NativeField:
        entity = self.get(entity_type)
        try:
            return entity.fields[field_key]
        except KeyError:
            raise ValidationFailedError(f"unknown field {field_key!r} on {entity_type}") from None

    def validate_against_models(self, models: dict[str, Any]) -> list[str]:
        """Boot check: every registry key must be a real column.

        Returns the list of problems. A non-empty list is a **boot failure**,
        not a warning — the same rule as ``role_permission.permission_key``.
        """
        problems: list[str] = []
        for entity_type, entity in sorted(self._entities.items()):
            model = models.get(entity.model_name)
            if model is None:
                problems.append(f"{entity_type}: no model named {entity.model_name!r} was supplied")
                continue
            columns = {c.key for c in model.__table__.columns}
            for key in sorted(entity.fields):
                if key not in columns:
                    problems.append(f"{entity_type}.{key}: no such column on {entity.model_name}")
        return problems


def assert_config_allowed(
    native: NativeField,
    *,
    field_key: str,
    is_visible: bool | None,
    is_required: bool | None,
    label_override: str | None,
) -> None:
    """Validate a ``field_config`` row against the registry, at write time.

    At write time and not at render time: a rejected config never reaches the
    resolver, so a bad row cannot quietly drop a required field from a form.
    """
    if is_visible is False and not native.hideable:
        raise ValidationFailedError(
            f"{field_key} cannot be hidden: {native.reason}",
            fields={field_key: "not hideable"},
        )
    if is_required is False and native.required:
        # Loosening would switch off form enforcement of a NOT NULL column, and
        # every create would 500 at the database instead of returning 422.
        raise ValidationFailedError(
            f"{field_key} is required by domain rule and cannot be made optional",
            fields={field_key: "requiredness may only be tightened"},
        )
    if label_override is not None and not native.renameable:
        raise ValidationFailedError(
            f"{field_key} cannot be relabelled: it appears in statutory output "
            "under its legal name",
            fields={field_key: "not renameable"},
        )


registry = FieldRegistry()
