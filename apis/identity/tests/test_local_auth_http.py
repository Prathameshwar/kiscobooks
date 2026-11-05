"""Limits that keep one caller from costing everyone else (docs/local-auth.md §6).

None of these need a database: they are about how much a stranger can make the service remember,
read or hold, which is exactly what an unauthenticated sign-in endpoint has to bound.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from billing_platform.db.session import create_engine
from billing_platform.rate_limit import WindowLimiter

from identity.local_auth import offload
from identity.local_auth.errors import TooManyAttemptsError
from identity.local_auth.http import SLOTS, throttle


def request_with(limiter: WindowLimiter) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(local_limiter=limiter)))


def test_the_throttle_table_cannot_be_filled_by_inventing_keys() -> None:
    """Else a few hundred requests a second make every first attempt anyone makes a 429."""
    limiter = WindowLimiter(capacity=65_536)
    request = request_with(limiter)
    for number in range(20_000):
        for bucket, key in (
            ("login-account", f"nobody{number}@attacker.example"),
            ("login-request", f"{number:043d}"),
        ):
            try:
                throttle(request, bucket, key, 10)
            except TooManyAttemptsError:
                pass  # a crowded slot; what matters is that the table stopped growing
    assert len(limiter._windows) <= 2 * SLOTS
    # Unrelated people still get in: a flood of invented keys crowds a few slots, not the table.
    refused = 0
    for number in range(500):
        try:
            throttle(request, "login-account", f"person{number}@example.test", 10)
        except TooManyAttemptsError:
            refused += 1
    assert refused < 50


def test_one_key_is_still_held_to_its_own_limit() -> None:
    limiter = WindowLimiter()
    request = request_with(limiter)
    for _ in range(10):
        throttle(request, "login-account", "asha@alpha.example", 10)
    with pytest.raises(TooManyAttemptsError):
        throttle(request, "login-account", "asha@alpha.example", 10)
    # The same text in another bucket is another budget.
    throttle(request, "login-request", "asha@alpha.example", 10)


def test_every_bucket_together_stays_inside_the_limiters_capacity() -> None:
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "identity"
    names = set()
    for module in ("api/local_auth.py", "api/oidc.py"):
        text = (source / module).read_text(encoding="utf-8")
        names |= {
            part.split('"')[1] for part in text.split("throttle(request, ")[1:] if '"' in part[:30]
        }
    assert names, "no throttle buckets found"
    assert len(names) * SLOTS < 65_536


def test_hashing_in_flight_can_never_hold_more_than_half_the_database_pool() -> None:
    """A sign-in keeps its connection while it hashes; the gateway authorizer needs the rest."""
    pool = create_engine("mysql+asyncmy://user@127.0.0.1/identity").sync_engine.pool
    capacity = pool.size() + pool._max_overflow  # type: ignore[attr-defined]
    assert offload.WORKERS + offload.QUEUE_LIMIT <= capacity // 2
