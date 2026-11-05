"""Resolve scoped field definitions/layout separately from actor authorization."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.custom_fields import CustomDefinition, validate_definitions
from billing_platform.errors import ValidationFailedError
from billing_platform.field_policy import FieldPolicyRule, resolve_field_effect
from billing_platform.fields import EntityFields, assert_config_allowed


@dataclass(frozen=True, slots=True)
class ScopedDefinition:
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    definition: CustomDefinition
    source_version: int


@dataclass(frozen=True, slots=True)
class FieldLayout:
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    source: Literal["native", "custom"]
    key: str
    visible: bool | None = None
    required: bool | None = None
    label: str | None = None
    order: int | None = None


@dataclass(frozen=True, slots=True)
class EffectiveField:
    source: Literal["native", "custom"]
    key: str
    label: str
    required: bool
    visible: bool
    order: int
    writable: bool
    definition: CustomDefinition | None = None


def resolve_custom_definitions(
    records: Iterable[ScopedDefinition],
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    native_fields: frozenset[str],
    option_sources: frozenset[str],
) -> tuple[CustomDefinition, ...]:
    """Company definition takes precedence, including an explicit inactive override.

    Company overrides cannot change the logical type or weaken tenant uniqueness.
    Source tombstones must already have removed their exact scoped projection;
    omission in a partial snapshot is not a tombstone.
    """
    tenant: dict[str, CustomDefinition] = {}
    company: dict[str, CustomDefinition] = {}
    for row in records:
        if row.tenant_id != tenant_id or row.company_id not in (None, company_id):
            continue
        target = tenant if row.company_id is None else company
        if row.source_version < 1 or row.definition.key in target:
            raise ValidationFailedError("ambiguous custom definition source")
        target[row.definition.key] = row.definition
    for key, override in company.items():
        original = tenant.get(key)
        if original is not None and (
            original.data_type != override.data_type
            or (
                original.validation.unique_within == "tenant"
                and override.validation.unique_within != "tenant"
            )
        ):
            raise ValidationFailedError("company definition weakens its logical field contract")
    resolved = tuple(sorted({**tenant, **company}.values(), key=lambda row: row.key))
    validate_definitions(resolved, native_fields=native_fields, option_sources=option_sources)
    return resolved


def resolve_layout(
    native: EntityFields,
    definitions: tuple[CustomDefinition, ...],
    layouts: Iterable[FieldLayout],
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    enabled_features: frozenset[str],
) -> tuple[EffectiveField, ...]:
    """Presentation result only. A hidden native field remains API writable/readable."""
    result: dict[tuple[str, str], EffectiveField] = {}
    for key, field in native.fields.items():
        if field.requires_feature is not None and field.requires_feature not in enabled_features:
            continue
        result[("native", key)] = EffectiveField(
            "native", key, key, field.required, True, field.order, True
        )
    for order, definition in enumerate(definitions):
        if definition.is_active:
            result[("custom", definition.key)] = EffectiveField(
                "custom",
                definition.key,
                definition.key,
                definition.validation.required,
                True,
                order,
                definition.data_type != "auto_number",
                definition,
            )
    rows = [
        row
        for row in layouts
        if row.tenant_id == tenant_id and row.company_id in (None, company_id)
    ]
    seen: set[tuple[uuid.UUID | None, str, str]] = set()
    for row in sorted(rows, key=lambda value: value.company_id is not None):
        identity = (row.company_id, row.source, row.key)
        if identity in seen:
            raise ValidationFailedError("ambiguous field layout source")
        seen.add(identity)
        pair = row.source, row.key
        if pair not in result:
            # Disabled known fields may retain configuration for later activation.
            known = (
                row.key in native.fields
                if row.source == "native"
                else any(d.key == row.key for d in definitions)
            )
            if not known:
                raise ValidationFailedError("field layout references an unregistered field")
            continue
        original = result[pair]
        if row.source == "native":
            assert_config_allowed(
                native.fields[row.key],
                field_key=row.key,
                is_visible=row.visible,
                is_required=row.required,
                label_override=row.label,
            )
        updated_definition = original.definition
        if updated_definition is not None and row.required is not None:
            updated_definition = updated_definition.model_copy(
                update={
                    "validation": updated_definition.validation.model_copy(
                        update={"required": original.required or row.required}
                    )
                }
            )
        result[pair] = replace(
            original,
            definition=updated_definition,
            visible=original.visible if row.visible is None else row.visible,
            required=original.required or bool(row.required),
            label=original.label if row.label is None else row.label,
            order=original.order if row.order is None else row.order,
        )
    return tuple(sorted(result.values(), key=lambda row: (row.order, row.source, row.key)))


def apply_field_access(
    fields: Iterable[EffectiveField],
    *,
    rules: Iterable[FieldPolicyRule],
    target: ScopePath,
) -> tuple[EffectiveField, ...]:
    """Apply actor access last; layout cannot grant read/write access."""
    policy = tuple(rules)
    output = []
    for field in fields:
        key = field.key if field.source == "native" else "custom_field:" + field.key
        if resolve_field_effect(policy, field_key=key, access="read", target=target) == "deny":
            continue
        output.append(
            replace(
                field,
                writable=field.writable
                and resolve_field_effect(policy, field_key=key, access="write", target=target)
                != "deny",
            )
        )
    return tuple(output)


def changed_values(previous: Mapping[str, object], current: Mapping[str, object]) -> frozenset[str]:
    """Changed keys after domain normalization; explicit clears differ from omission."""
    return frozenset(
        key
        for key in previous.keys() | current.keys()
        if not _equivalent(previous.get(key), current.get(key))
    )


def _equivalent(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equivalent(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _equivalent(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right
