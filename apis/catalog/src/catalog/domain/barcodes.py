"""Pure product-code allocation, GTIN equivalence and bounded GS1 scan parsing."""

import base64
import calendar
import uuid
from dataclasses import dataclass

from billing_platform.errors import ValidationFailedError

from catalog.domain.product_authoring import validate_barcode


@dataclass(frozen=True)
class ParsedScan:
    code: str
    lot: str | None = None
    expiry_yymmdd: str | None = None
    serial: str | None = None
    gs1: bool = False


def generate_internal_value(value: uuid.UUID) -> str:
    """Opaque company-local Code 128 data, never an unlicensed GS1 number."""
    return "I" + base64.b32encode(value.bytes).decode("ascii").rstrip("=")


def gtin_aliases(value: str) -> tuple[str, ...]:
    validate_barcode(value, "GTIN")
    padded = value.zfill(14)
    return tuple(
        candidate
        for length in (8, 12, 13, 14)
        if (candidate := padded[-length:]).zfill(14) == padded and _valid_gtin(candidate)
    )


def _valid_gtin(value: str) -> bool:
    try:
        validate_barcode(value, "GTIN")
    except ValidationFailedError:
        return False
    return True


def parse_scan(value: str) -> ParsedScan:
    """Parse plain product data or the supported GS1-128 element-string subset.

    Only AI 01/10/17/21 is admitted. Unknown or duplicate AIs fail closed rather than
    silently losing stock-tracking information. Date is a raw hint: the stock owner must
    interpret its century and verify it before any posting.
    """
    if not value or len(value) > 256:
        raise ValidationFailedError("scan data must contain 1-256 characters")
    if value.startswith("]C0"):
        value = value[3:]
    elif value.startswith("]") and len(value) >= 3:
        if value[1:3] != "C1":
            raise ValidationFailedError("scanner symbology identifier is unsupported")
    if not value.startswith("]C1"):
        validate_barcode(value, "CODE128")
        return ParsedScan(value)
    data = value[3:]
    if not data or any(ord(char) > 126 or (ord(char) < 32 and char != "\x1d") for char in data):
        raise ValidationFailedError("GS1 scan has unsupported characters")
    fields: dict[str, str] = {}
    position = 0
    while position < len(data):
        if data[position] == "\x1d" or position + 2 > len(data):
            raise ValidationFailedError("GS1 scan has an invalid separator or AI")
        ai = data[position : position + 2]
        position += 2
        if ai in fields or ai not in {"01", "10", "17", "21"}:
            raise ValidationFailedError("GS1 scan has a repeated or unsupported AI")
        if ai in {"01", "17"}:
            size = 14 if ai == "01" else 6
            field = data[position : position + size]
            position += size
            if len(field) != size or not field.isascii() or not field.isdigit():
                raise ValidationFailedError("GS1 fixed-length AI is invalid")
        else:
            end = data.find("\x1d", position)
            if end < 0:
                end = len(data)
            field = data[position:end]
            if end < len(data) and end == len(data) - 1:
                raise ValidationFailedError("GS1 scan has a trailing separator")
            position = end + (end < len(data))
            if not field or len(field) > 20:
                raise ValidationFailedError("GS1 variable-length AI is invalid")
        fields[ai] = field
    if "01" not in fields:
        raise ValidationFailedError("GS1 product scan requires AI 01")
    validate_barcode(fields["01"], "GTIN")
    expiry = fields.get("17")
    if expiry is not None:
        year, month, day = int(expiry[:2]), int(expiry[2:4]), int(expiry[4:6])
        if not 1 <= month <= 12 or day > max(
            calendar.monthrange(2000 + year, month)[1],
            calendar.monthrange(2100 + year, month)[1],
        ):
            raise ValidationFailedError("GS1 expiry date is invalid")
    return ParsedScan(
        code=fields["01"],
        lot=fields.get("10"),
        expiry_yymmdd=expiry,
        serial=fields.get("21"),
        gs1=True,
    )
