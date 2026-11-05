"""Explicit nested patch semantics for native draft aggregates."""

from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from catalog.schemas.configuration import DraftInput, DraftPatch


def merge_draft(current: DraftInput, patch: DraftPatch) -> DraftInput:
    values = current.model_dump()
    changes = patch.model_dump(exclude_unset=True, exclude={"expected_version"})
    for section in ("options", "profiles", "pricing"):
        if section not in changes:
            continue
        supplied = changes[section]
        merged = {**values[section], **supplied}
        for field, mode in supplied.items():
            if not field.endswith("_mode"):
                continue
            prefix = field.removesuffix("_mode")
            sibling = prefix + ("_default" if section == "options" else "_id")
            retained_mode = "OPTIONAL" if section == "options" else "VALUE"
            if section != "pricing" and mode != retained_mode and sibling not in supplied:
                merged[sibling] = None
        changes[section] = merged
    try:
        return DraftInput.model_validate({**values, **changes})
    except ValidationError as exc:
        raise ValidationFailedError(
            "configuration patch contains inconsistent native values"
        ) from exc
