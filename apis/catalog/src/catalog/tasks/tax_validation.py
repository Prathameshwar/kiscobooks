"""Validate persisted native tax definitions before they enter resolution."""

from collections.abc import Sequence
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from pydantic import ValidationError

from catalog.domain.tax import validate_components
from catalog.schemas.tax import ClassificationMatch, ComponentInput


def stored_components(
    applicability: str, treatment: str, values: Sequence[Any]
) -> list[ComponentInput]:
    try:
        entries = [
            ComponentInput.model_validate(
                {key: getattr(value, key) for key in ComponentInput.model_fields}
            )
            for value in values
        ]
        validate_components(applicability, treatment, entries)
    except (ValidationError, ValidationFailedError) as exc:
        raise ConflictError("stored tax components require a reviewed correction") from exc
    return entries


def stored_match(value: Any) -> ClassificationMatch:
    try:
        return ClassificationMatch.model_validate(
            {key: getattr(value, key) for key in ClassificationMatch.model_fields}
        )
    except ValidationError as exc:
        raise ConflictError("stored tax applicability requires a reviewed correction") from exc
