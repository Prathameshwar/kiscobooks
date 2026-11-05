"""UUIDv7 generation.

Ordering is the point. A PK that goes backwards splits an InnoDB page on every
insert, which is exactly what v4 does and what v7 is here to avoid — so the
ordering tests freeze the clock and drive the counter to exhaustion rather than
trusting a happy-path loop.
"""

from __future__ import annotations

import time
import uuid

import pytest

from billing_platform import ids
from billing_platform.ids import timestamp_ms, uuid7, uuid7_bytes

_FROZEN_MS = 1_700_000_000_000


def _freeze(monkeypatch: pytest.MonkeyPatch, at_ms: int, *, last_ms: int, counter: int) -> None:
    monkeypatch.setattr(ids, "_last_ms", last_ms)
    monkeypatch.setattr(ids, "_counter", counter)
    monkeypatch.setattr(ids, "_now_ms", lambda: at_ms)


def test_version_and_variant_are_rfc9562_compliant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_ids_are_monotonic_within_a_millisecond() -> None:
    """A thousand ids back-to-back land in the same millisecond, so this
    exercises the counter path rather than the timestamp path."""
    values = [uuid7() for _ in range(1000)]
    assert values == sorted(values)
    assert len(set(values)) == 1000


def test_bytes_form_is_sixteen_bytes() -> None:
    assert len(uuid7_bytes()) == 16


def test_timestamp_is_recoverable() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000
    assert before <= timestamp_ms(value) <= after + 1


def test_timestamp_rejects_a_non_v7_uuid() -> None:
    with pytest.raises(ValueError, match="not a UUIDv7"):
        timestamp_ms(uuid.uuid4())


def test_counter_exhaustion_steps_into_the_next_millisecond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4096 ids in one millisecond exhausts the counter. Wrapping it would break
    ordering, so the generator borrows from the next millisecond instead."""
    _freeze(monkeypatch, _FROZEN_MS, last_ms=_FROZEN_MS, counter=ids._COUNTER_MAX)

    first = ids.uuid7()
    second = ids.uuid7()

    assert timestamp_ms(first) == _FROZEN_MS + 1
    assert second > first


def test_ids_stay_monotonic_across_counter_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a frozen clock plus 10k ids exhausts the counter repeatedly.

    Each exhaustion borrows the next millisecond, and the *following* call then
    sees a wall clock that is behind ``_last_ms``. Reseeding the counter randomly
    on that path handed out ids that sorted before ones already written.
    """
    _freeze(monkeypatch, _FROZEN_MS, last_ms=_FROZEN_MS, counter=0)

    values = [ids.uuid7() for _ in range(10_000)]

    assert values == sorted(values)
    assert len(set(values)) == 10_000


def test_a_clock_that_moves_backwards_does_not_move_ids_backwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NTP stepping the clock back must not produce an id that sorts before one
    already written — it would land in the wrong place in the InnoDB cluster."""
    _freeze(monkeypatch, _FROZEN_MS - 100, last_ms=_FROZEN_MS, counter=0)

    first = ids.uuid7()
    second = ids.uuid7()

    assert timestamp_ms(first) == _FROZEN_MS
    assert second > first


def test_time_moving_forward_reseeds_the_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh random seed is only safe once the timestamp itself has advanced."""
    _freeze(monkeypatch, _FROZEN_MS + 1, last_ms=_FROZEN_MS, counter=ids._COUNTER_MAX)

    value = ids.uuid7()

    assert timestamp_ms(value) == _FROZEN_MS + 1
    assert ids._counter <= (1 << ids._COUNTER_SEED_BITS) - 1
