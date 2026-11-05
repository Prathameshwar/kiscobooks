"""Exact variant identity and product identifier validation without storage."""

import hashlib
import uuid
from collections.abc import Mapping

from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json


def variant_identity(
    axes: Mapping[uuid.UUID, frozenset[uuid.UUID]], selected: Mapping[uuid.UUID, uuid.UUID]
) -> tuple[bytes, bytes]:
    if not axes or len(axes) > 8 or set(selected) != set(axes):
        raise ValidationFailedError("a variant requires exactly one value for every declared axis")
    if any(value not in axes[axis] for axis, value in selected.items()):
        raise ValidationFailedError("variant uses an option outside its family axis")
    canonical = canonical_json({str(key): str(value) for key, value in sorted(selected.items())})
    # At most eight UUID pairs fit comfortably within the 2,048-byte native column.
    return hashlib.sha256(canonical).digest(), canonical


def validate_barcode(value: str, symbology: str) -> None:
    if (
        not value
        or len(value) > 128
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) > 126 for char in value)
    ):
        raise ValidationFailedError("product identifiers require bounded printable ASCII")
    if symbology == "GTIN":
        if len(value) not in {8, 12, 13, 14} or not value.isdigit():
            raise ValidationFailedError("GTIN length or characters are invalid")
        weighted = sum(
            int(char) * (3 if index % 2 == 0 else 1)
            for index, char in enumerate(reversed(value[:-1]))
        )
        if (10 - weighted % 10) % 10 != int(value[-1]):
            raise ValidationFailedError("GTIN check digit is invalid")
