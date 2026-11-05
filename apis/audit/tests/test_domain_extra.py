"""Edge cases in the pure domain: canonicalization types and the category guard."""

from __future__ import annotations

import uuid

import pytest

from audit.domain import categories
from audit.domain.hash_chain import compute_row_hash


def test_is_valid_category() -> None:
    assert categories.is_valid_category("security")
    assert not categories.is_valid_category("bogus")


def test_canonicalizes_nested_lists_and_bytes() -> None:
    # ``changes``/``context`` are hashed fields and may nest lists and byte values; each
    # must have a stable, collision-free canonical form.
    a = compute_row_hash(prev_hash=None, fields={"context": {"ids": [1, 2], "raw": b"\x00\x01"}})
    b = compute_row_hash(prev_hash=None, fields={"context": {"ids": [1, 2], "raw": b"\x00\x01"}})
    assert a == b
    different = compute_row_hash(
        prev_hash=None, fields={"context": {"ids": [1, 3], "raw": b"\x00\x01"}}
    )
    assert a != different


def test_fractional_numbers_are_hashable() -> None:
    # Regression: a float in changes/context must be recorded, not raise (which would
    # dead-letter the event). It also hashes deterministically.
    fields = {"changes": {"tax_rate": {"from": 18.0, "to": 12.5}}}
    a = compute_row_hash(prev_hash=None, fields=fields)
    b = compute_row_hash(prev_hash=None, fields=fields)
    assert a == b
    changed = compute_row_hash(
        prev_hash=None, fields={"changes": {"tax_rate": {"from": 18.0, "to": 5.0}}}
    )
    assert a != changed


def test_uuid_and_string_do_not_collide() -> None:
    ident = uuid.UUID(int=7)
    as_uuid = compute_row_hash(prev_hash=None, fields={"entity_id": ident})
    as_str = compute_row_hash(prev_hash=None, fields={"entity_id": str(ident)})
    assert as_uuid != as_str  # tagged, so a string can't impersonate a UUID


def test_non_canonicalizable_value_raises() -> None:
    with pytest.raises(TypeError):
        compute_row_hash(prev_hash=None, fields={"context": {"bad": {1, 2, 3}}})
