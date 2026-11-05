"""Explicit compatible value mapping for later source-linked document conversions.

Returns proposed target values only. The normal target-write path must still check
requiredness/visibility/current options, allocate new claims/numbers and save source
revision/line provenance atomically. No document conversion is activated by this helper.
"""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from billing_platform.custom_fields import MAX_DEFINITIONS, CustomDefinition, scalar_value
from billing_platform.errors import PermissionDeniedError, ValidationFailedError


def mapped_values(
    values: Mapping[str, Any],
    source: Mapping[str, CustomDefinition],
    target: Mapping[str, CustomDefinition],
    mapping: Mapping[str, str],
    *,
    readable: frozenset[str],
    writable: frozenset[str],
    currencies: frozenset[str],
) -> dict[str, Any]:
    if len(mapping) > MAX_DEFINITIONS or len(set(mapping.values())) != len(mapping):
        raise ValidationFailedError("custom conversion mapping exceeds bounds or repeats a target")
    if not mapping.keys() <= readable or not set(mapping.values()) <= writable:
        raise PermissionDeniedError("custom conversion fields are not authorized")
    copied: dict[str, Any] = {}
    for source_key, target_key in mapping.items():
        left, right = source.get(source_key), target.get(target_key)
        if left is None or right is None or left.key != source_key or right.key != target_key:
            raise ValidationFailedError("custom conversion definition is unavailable")
        if (
            not right.is_active
            or left.data_type != right.data_type
            or right.data_type == "auto_number"
            or right.validation.unique_within != "none"
            or left.option_source_key != right.option_source_key
            or (left.depends_on_key is None) != (right.depends_on_key is None)
            or (
                left.depends_on_key is not None
                and mapping.get(left.depends_on_key) != right.depends_on_key
            )
        ):
            raise ValidationFailedError("custom conversion definitions are incompatible")
        if source_key not in values:
            continue
        value = values[source_key]
        try:
            normalized = (
                None if value is None else scalar_value(right, value, currencies=currencies)
            )
        except (ValueError, TypeError) as exc:
            raise ValidationFailedError("custom conversion value is incompatible") from exc
        if normalized is not None and right.data_type in {"select", "multi_select"}:
            selected = set(normalized) if right.data_type == "multi_select" else {normalized}
            if not selected <= {choice.value for choice in right.choices if choice.is_active}:
                raise ValidationFailedError("custom conversion option is unavailable")
        copied[target_key] = deepcopy(normalized)
    return copied
