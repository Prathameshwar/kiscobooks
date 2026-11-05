"""Frozen display facts and exact, locale-independent server presentation.

Date tokens and decimal fixtures are shared with @janso/ui. This module never
changes stored values; CSV retains canonical amounts and ISO business dates.
"""

import datetime as dt
import re
from decimal import Decimal, InvalidOperation, localcontext
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from billing_platform.money import RoundingMode


class DisplayConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    company_label: str = Field(min_length=1, max_length=255)
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount_precision: int = Field(strict=True, ge=0, le=4)
    quantity_precision: int = Field(strict=True, ge=0, le=4)
    rounding_mode: RoundingMode
    date_format: str = Field(min_length=1, max_length=20)
    datetime_format: str = Field(min_length=1, max_length=30)
    digit_grouping: Literal["indian", "western"]
    decimal_separator: str = Field(min_length=1, max_length=2)
    thousands_separator: str = Field(max_length=2)
    negative_format: Literal["minus", "parentheses"]
    currency_display: Literal["symbol", "code", "none"]
    currency_symbol_position: Literal["prefix", "suffix"]
    currency_symbol_override: str | None = Field(default=None, max_length=8)
    timezone: str = Field(min_length=1, max_length=100)
    locale: str = Field(min_length=1, max_length=35)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown display timezone") from exc
        return value


def number(
    value: Decimal | str | int | None, config: DisplayConfiguration, *, quantity: bool = False
) -> str:
    if value is None:
        return "\u2014"
    if isinstance(value, bool) or not isinstance(value, Decimal | str | int):
        raise ValueError("display requires an exact decimal")
    if len(str(value)) > 128:
        raise ValueError("display number exceeds its bound")
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid display decimal") from exc
    if not decimal.is_finite() or decimal.adjusted() >= 34:
        raise ValueError("display number exceeds DECIMAL(38,4)")
    precision = config.quantity_precision if quantity else config.amount_precision
    with localcontext() as arithmetic:
        arithmetic.prec = 40
        rounded = decimal.quantize(
            Decimal(1).scaleb(-precision), rounding=config.rounding_mode.decimal_rounding
        )
        text = format(abs(rounded), "f")
    integer, _, fraction = text.partition(".")
    groups = [integer[-3:]]
    remaining = integer[:-3]
    width = 2 if config.digit_grouping == "indian" else 3
    while remaining:
        groups.append(remaining[-width:])
        remaining = remaining[:-width]
    text = config.thousands_separator.join(reversed(groups))
    if precision:
        text += config.decimal_separator + fraction
    if rounded < 0:
        text = f"({text})" if config.negative_format == "parentheses" else "-" + text
    return text


_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_TOKENS = re.compile(r"'[^']*'?|yyyy|yy|MMMM|MMM|MM|M|dd|d|HH|mm|ss")


def date(
    value: str | dt.date | None, config: DisplayConfiguration, *, timestamp: bool = False
) -> str:
    if value is None:
        return "\u2014"
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value) if "T" in value else dt.date.fromisoformat(value)
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            raise ValueError("display timestamp requires an explicit timezone")
        value = value.astimezone(ZoneInfo(config.timezone))
    pattern = config.datetime_format if timestamp else config.date_format
    tokens = {
        "yyyy": f"{value.year:04d}",
        "yy": f"{value.year % 100:02d}",
        "MMMM": _MONTHS[value.month - 1],
        "MMM": _MONTHS[value.month - 1][:3],
        "MM": f"{value.month:02d}",
        "M": str(value.month),
        "dd": f"{value.day:02d}",
        "d": str(value.day),
        "HH": f"{value.hour if isinstance(value, dt.datetime) else 0:02d}",
        "mm": f"{value.minute if isinstance(value, dt.datetime) else 0:02d}",
        "ss": f"{value.second if isinstance(value, dt.datetime) else 0:02d}",
    }

    def replace(match: re.Match[str]) -> str:
        token = match.group()
        if token.startswith("'"):
            inner = token[1:-1] if len(token) > 1 and token.endswith("'") else token[1:]
            return inner or "'"
        return tokens[token]

    return _TOKENS.sub(replace, pattern)
