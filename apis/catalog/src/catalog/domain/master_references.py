"""Code-owned normalization for alternate master identities."""

import unicodedata

from billing_platform.errors import ValidationFailedError

NORMALIZATION_VERSION = 1


def valid_text(value: str, maximum: int) -> None:
    if not 1 <= len(value) <= maximum or any(
        unicodedata.category(char).startswith("C") for char in value
    ):
        raise ValidationFailedError("reference text is empty, too long or contains controls")


def normalized_alias(value: str) -> tuple[str, str]:
    valid_text(value, 100)
    display = value.strip()
    canonical = " ".join(unicodedata.normalize("NFKC", display).casefold().split())
    valid_text(canonical, 200)
    return display, canonical


def external_key(value: str) -> str:
    valid_text(value, 200)
    if value != value.strip():
        raise ValidationFailedError("external identifiers cannot contain surrounding whitespace")
    return value
