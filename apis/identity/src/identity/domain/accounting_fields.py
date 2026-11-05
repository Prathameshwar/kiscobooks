"""Versioned native field contract supplied by Accounting, independent of its models."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from billing_platform.errors import ValidationFailedError
from billing_platform.fields import NativeField


@lru_cache(maxsize=1)
def contracts() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "data/accounting_fields.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def contract(entity: str) -> dict[str, Any]:
    result = contracts().get(entity)
    if result is None:
        raise ValidationFailedError("entity field contract is not supported")
    return cast(dict[str, Any], result)


def native_field(entity: str, key: str) -> NativeField:
    field = contract(entity)["forms"].get(key)
    if field is None:
        raise ValidationFailedError("field layout is not supported")
    return NativeField(
        required=field["required"],
        hideable=field["hideable"],
        reason=None if field["hideable"] else "required or immutable Accounting field",
    )
