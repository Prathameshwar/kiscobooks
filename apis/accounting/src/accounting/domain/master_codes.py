"""Optional user-entered identities; storage always receives a nonempty code."""

from typing import Any

from billing_platform.errors import ValidationFailedError

CODE_DESCRIPTION = (
    "Leave blank to generate a unique eight-character code. "
    "Manual codes allow printable text up to 40 characters and are fixed after creation."
)


def optional_code(value: Any, *, field: str = "code") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationFailedError("Code is invalid", fields={field: "Enter Code as text."})
    code = value.strip()
    if not code:
        return None
    if len(code) > 40 or any(ord(char) < 32 or ord(char) == 127 for char in code):
        raise ValidationFailedError(
            "Code is invalid",
            fields={field: "Use printable text up to 40 characters; remove control characters."},
        )
    return code
