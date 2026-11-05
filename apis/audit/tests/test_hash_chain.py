"""The tamper-evidence chain (docs/audit.md §4.2) — pure, no database."""

from __future__ import annotations

import datetime as dt
import uuid

from audit.domain import hash_chain


def _fields(seq: int, *, action: str = "created") -> dict[str, object]:
    return {
        "tenant_id": uuid.UUID(int=1),
        "sequence": seq,
        "occurred_at": dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.UTC),
        "category": "admin",
        "action": action,
        "entity_type": "user",
        "entity_id": uuid.UUID(int=seq),
        "changes": {"name": {"from": "a", "to": "b"}},
        "message_id": uuid.UUID(int=100 + seq),
    }


def test_row_hash_is_deterministic() -> None:
    a = hash_chain.compute_row_hash(prev_hash=None, fields=_fields(1))
    b = hash_chain.compute_row_hash(prev_hash=None, fields=_fields(1))
    assert a == b
    assert len(a) == 32


def test_row_hash_depends_on_prev_hash() -> None:
    without = hash_chain.compute_row_hash(prev_hash=None, fields=_fields(2))
    with_prev = hash_chain.compute_row_hash(prev_hash=b"\x01" * 32, fields=_fields(2))
    assert without != with_prev


def test_missing_field_hashes_as_none() -> None:
    fields = _fields(1)
    del fields["changes"]  # absent
    explicit = dict(_fields(1))
    explicit["changes"] = None
    from_absent = hash_chain.compute_row_hash(prev_hash=None, fields=fields)
    from_explicit = hash_chain.compute_row_hash(prev_hash=None, fields=explicit)
    assert from_absent == from_explicit


def _chain(count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    prev: bytes | None = None
    for seq in range(1, count + 1):
        fields = _fields(seq)
        row_hash = hash_chain.compute_row_hash(prev_hash=prev, fields=fields)
        rows.append({**fields, "prev_hash": prev, "row_hash": row_hash})
        prev = row_hash
    return rows


def test_intact_chain_has_no_breaks() -> None:
    assert hash_chain.verify_chain(_chain(4)) == []


def test_tampered_content_is_detected() -> None:
    rows = _chain(4)
    rows[2]["action"] = "deleted"  # edit the content without recomputing the hash
    breaks = hash_chain.verify_chain(rows)
    assert any(b.sequence == 3 for b in breaks)


def test_deleted_row_breaks_sequence_and_link() -> None:
    rows = _chain(4)
    del rows[1]  # drop sequence 2
    breaks = hash_chain.verify_chain(rows)
    assert breaks  # a gap and a prev_hash mismatch both surface
