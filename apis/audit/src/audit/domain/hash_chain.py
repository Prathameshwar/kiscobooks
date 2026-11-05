"""The per-tenant tamper-evidence chain (docs/audit.md §4.2).

Each row stores ``prev_hash`` (the previous row's ``row_hash`` for the same tenant) and
``row_hash`` = SHA-256 over a canonical serialization of the row's content **plus**
``prev_hash``. Any retroactive edit or deletion breaks the chain from that point on and
is detectable by :func:`verify_chain`.

Cheap only because there is a single writer per tenant (§4.2) — one consumer assigns
``sequence`` and computes the chain in order. This module is pure: the fields it hashes
are passed in, so it is fully testable without a database and produces the same bytes on
every platform (no locale, no float, no dict-ordering dependence).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any


def _canonical(value: Any) -> Any:
    """Coerce a field value to a JSON-stable, type-tagged form.

    UUIDs, datetimes and bytes have no canonical JSON form, and two of them would
    otherwise collide with a string that happens to match — so each is tagged. The
    result feeds ``json.dumps(sort_keys=True)``, which fixes key order.
    """
    if value is None or isinstance(value, bool | int | float | str):
        # ``float`` is a first-class JSON number, so ``changes``/``context`` values may be
        # fractional (a tax rate, a quantity). It round-trips deterministically: both the
        # write side and the verifier hold the same IEEE-754 double and serialize it with
        # the same ``json.dumps``. Omitting it dead-lettered the event instead of recording
        # it — a silent hole in the trail. JSON forbids NaN/Inf, so no non-finite reaches here.
        return value
    if isinstance(value, uuid.UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, dt.datetime):
        # Normalize to UTC microseconds so a tz-aware and its equivalent hash alike.
        return {"__dt__": value.astimezone(dt.UTC).isoformat()}
    if isinstance(value, bytes):
        return {"__b__": value.hex()}
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    raise TypeError(f"non-canonicalizable field of type {type(value).__name__}")


#: The row fields the hash covers, in a fixed set. Presentation-only columns
#: (``ingested_at`` — the consumer's clock — and the hashes themselves) are excluded so
#: the chain reflects the recorded change, not when it happened to be consumed.
HASHED_FIELDS: tuple[str, ...] = (
    "tenant_id",
    "sequence",
    "occurred_at",
    "actor_type",
    "actor_user_id",
    "on_behalf_of_user_id",
    "actor_ip",
    "actor_user_agent",
    "api_client_id",
    "company_id",
    "department_id",
    "category",
    "action",
    "entity_type",
    "entity_id",
    "changes",
    "context",
    "reason",
    "source_service",
    "trace_id",
    "request_id",
    "message_id",
)


def compute_row_hash(*, prev_hash: bytes | None, fields: dict[str, Any]) -> bytes:
    """SHA-256 over ``prev_hash`` followed by the canonical content of ``fields``.

    Missing keys are treated as ``None`` so a caller cannot change the hash by omitting a
    field that was null anyway. Unknown extra keys are ignored: only :data:`HASHED_FIELDS`
    participate, so adding a presentation column later does not rewrite history.
    """
    content = {name: _canonical(fields.get(name)) for name in HASHED_FIELDS}
    body = json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    hasher = hashlib.sha256()
    hasher.update(prev_hash if prev_hash is not None else b"")
    hasher.update(b"\x00")  # domain separator between the link and the content
    hasher.update(body)
    return hasher.digest()


@dataclass(frozen=True, slots=True)
class ChainBreak:
    """A detected discontinuity, for the verification job's alert (§4.2)."""

    sequence: int
    reason: str


def verify_chain(
    rows: list[dict[str, Any]],
    *,
    initial_prev: bytes | None = None,
    initial_sequence: int | None = None,
) -> list[ChainBreak]:
    """Recompute the chain over ``rows`` (ordered by ``sequence``) and report breaks.

    Checks three things per row: ``sequence`` is contiguous, ``prev_hash`` equals the
    prior row's ``row_hash``, and ``row_hash`` recomputes from the content. An empty or
    single-tenant slice is expected; the caller supplies one tenant's rows in order.
    """
    breaks: list[ChainBreak] = []
    expected_prev: bytes | None = initial_prev
    expected_sequence: int | None = initial_sequence
    for row in rows:
        seq = int(row["sequence"])
        if expected_sequence is not None and seq != expected_sequence + 1:
            breaks.append(ChainBreak(seq, f"sequence gap: expected {expected_sequence + 1}"))
        stored_prev = row.get("prev_hash")
        if stored_prev != expected_prev:
            breaks.append(ChainBreak(seq, "prev_hash does not match the prior row_hash"))
        recomputed = compute_row_hash(prev_hash=stored_prev, fields=row)
        if recomputed != row.get("row_hash"):
            breaks.append(ChainBreak(seq, "row_hash does not match recomputed content"))
        expected_prev = row.get("row_hash")
        expected_sequence = seq
    return breaks
