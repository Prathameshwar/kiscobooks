"""Exact physical quantity/value wire type, shared by stock capture contracts."""

import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer, WithJsonSchema


def decimal_string(value: Any) -> Any:
    if not isinstance(value, str | Decimal):
        raise ValueError("stock quantities and values require exact decimal strings")
    if isinstance(value, str) and (
        len(value) > 64 or not re.fullmatch(r"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)", value)
    ):
        raise ValueError("stock decimals use ordinary decimal text without exponent or separators")
    return value


Exact = Annotated[
    Decimal,
    BeforeValidator(decimal_string),
    WithJsonSchema({"type": "string"}, mode="validation"),
    PlainSerializer(lambda value: format(value, ".4f"), return_type=str, when_used="json"),
    Field(max_digits=19, decimal_places=4, allow_inf_nan=False),
]
