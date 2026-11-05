"""UUIDv7 generation (RFC 9562 §5.7).

Python 3.12 has no ``uuid.uuid7`` (it arrives in 3.14), and this is ~40 lines,
so we implement it rather than take a dependency (CLAUDE.md §5.15).

Layout::

    0                   1                   2                   3
    |unix_ts_ms (48 bits)                          |ver|rand_a (12)|
    |var|                    rand_b (62 bits)                      |

Time-ordered, so it clusters well as an InnoDB primary key — which is the whole
reason the platform uses v7 rather than v4.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid

_VERSION = 0x7
_VARIANT = 0b10

# 12 bits of rand_a are used as a monotonic counter within the same millisecond,
# so ids generated in a tight loop stay ordered. Seeded randomly below 2**11 to
# leave headroom to increment without overflowing into the next millisecond.
_COUNTER_BITS = 12
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1
_COUNTER_SEED_BITS = 11

_lock = threading.Lock()
_last_ms = -1
_counter = 0


def _now_ms() -> int:
    """Wall clock in milliseconds.

    A named seam so the ordering tests can freeze or rewind time without
    monkeypatching the ``time`` module for the whole process.
    """
    return time.time_ns() // 1_000_000


def uuid7() -> uuid.UUID:
    """Return a new time-ordered UUIDv7."""
    global _last_ms, _counter

    with _lock:
        ms = _now_ms()
        if ms > _last_ms:
            # Time moved forward. A fresh random seed is safe here and adds
            # entropy, because the higher timestamp already orders this id after
            # every id handed out so far.
            _last_ms = ms
            _counter = secrets.randbits(_COUNTER_SEED_BITS)
        else:
            # Same millisecond, *or* the clock is behind `_last_ms` — because NTP
            # stepped it back, or because a previous exhausted counter already
            # borrowed from a future millisecond. In every one of those cases the
            # timestamp is held and the counter advances: reseeding it randomly
            # would hand out an id that sorts before one already written, and a
            # PK that goes backwards is a page split on every insert.
            ms = _last_ms
            if _counter >= _COUNTER_MAX:
                # Counter exhausted: step into the next millisecond rather than
                # wrap, and restart the counter at zero so the borrowed
                # millisecond stays ordered too.
                ms += 1
                _last_ms = ms
                _counter = 0
            else:
                _counter += 1
        counter = _counter

    value = (ms & 0xFFFFFFFFFFFF) << 80
    value |= _VERSION << 76
    value |= (counter & _COUNTER_MAX) << 64
    value |= _VARIANT << 62
    value |= secrets.randbits(62)
    return uuid.UUID(int=value)


def uuid7_bytes() -> bytes:
    """Return a new UUIDv7 as the 16 raw bytes stored in a ``BINARY(16)`` column."""
    return uuid7().bytes


def timestamp_ms(value: uuid.UUID) -> int:
    """Extract the embedded millisecond timestamp from a UUIDv7."""
    if value.version != 7:
        raise ValueError(f"not a UUIDv7: version={value.version}")
    return value.int >> 80
