"""Conservative stock-date, hold, expiry and quantity rules selected by the user."""

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from billing_platform.errors import ConflictError, ValidationFailedError

from accounting.domain.stock_costing import exact


def posting_day(
    day: dt.date, *, now: dt.datetime, timezone: str, last_posted_day: dt.date | None
) -> None:
    if now.tzinfo is None:
        raise ValueError("stock eligibility needs an aware clock")
    if day > now.astimezone(ZoneInfo(timezone)).date():
        raise ValidationFailedError("physical stock cannot be posted before its movement date")
    if last_posted_day is not None and day < last_posted_day:
        raise ConflictError("backdated stock would alter a later posted warehouse cost pool")


def issue_eligible(
    *,
    day: dt.date,
    active: bool,
    held: bool,
    manufactured_on: dt.date | None,
    expires_on: dt.date | None,
    minimum_remaining_life_days: int | None,
) -> None:
    if not active or held:
        raise ConflictError("retired or held stock cannot be issued")
    if manufactured_on is not None and day < manufactured_on:
        raise ConflictError("stock cannot be issued before manufacture")
    if expires_on is not None and day > expires_on:
        raise ConflictError("expired stock cannot be issued")
    if minimum_remaining_life_days is not None and minimum_remaining_life_days > 0:
        if expires_on is None or (expires_on - day).days < minimum_remaining_life_days:
            raise ConflictError("stock does not meet its minimum remaining shelf life")


def quantity(value: Decimal, *, increment: Decimal, serialized: bool = False) -> None:
    exact(value, positive=True)
    exact(increment, positive=True)
    if value % increment:
        raise ValidationFailedError("stock quantity does not fit its published base-unit step")
    if serialized and value != value.to_integral_value():
        raise ValidationFailedError("serialized units cannot have a fractional quantity")
