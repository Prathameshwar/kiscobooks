"""Scalar encoding for service-owned allowlisted audit evidence."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any


def scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal | uuid.UUID | int | str):
        return str(value)
    raise ValueError("unsupported audit scalar")
