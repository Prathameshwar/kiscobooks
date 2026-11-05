from __future__ import annotations

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.pagination import CursorCodec, PageRequest, validate_sort


def test_cursor_round_trip_and_context_binding() -> None:
    codec = CursorCodec(b"x" * 32, context="deliveries")
    token = codec.encode({"created_at": "2026-01-01T00:00:00Z", "id": "7"})
    assert codec.decode(token)["id"] == "7"
    with pytest.raises(ValidationFailedError):
        CursorCodec(b"x" * 32, context="requests").decode(token)


def test_cursor_rejects_tampering() -> None:
    codec = CursorCodec(b"x" * 32, context="deliveries")
    token = codec.encode({"id": "7"})
    with pytest.raises(ValidationFailedError):
        codec.decode(token[:-2] + "aa")


def test_page_and_sort_are_bounded() -> None:
    assert PageRequest().limit == 50
    assert validate_sort(
        "-created_at", allowed=frozenset({"created_at"}), default="created_at"
    ) == (
        "created_at",
        True,
    )
    with pytest.raises(ValidationFailedError):
        PageRequest(limit=201)
    with pytest.raises(ValidationFailedError):
        validate_sort("secret", allowed=frozenset({"created_at"}), default="created_at")
