"""Password hashing off the event loop.

argon2id is meant to be slow: about 140 ms and 64 MiB per hash at production cost. Run inline it
would stall every other request in the worker for that long — and Identity is the gateway's
authorizer, so a stalled worker stalls the platform. argon2-cffi releases the GIL while it hashes,
so a small thread pool gives real parallelism without a broker round-trip (docs/local-auth.md §6;
the choice over Celery for this one request-path task is recorded in the tech-stack decision log).

Two bounds keep the pool from being a new way to hurt the service: at most ``WORKERS`` hashes run at
once (memory is ``WORKERS`` x 64 MiB at most), and when ``QUEUE_LIMIT`` more are already waiting the
caller is refused at once with a 429 rather than joining an unbounded queue.

The total also has to stay well under the database pool. A request keeps its connection while its
hash runs (a failed guess is counted under a row lock), so every hash in flight holds one. The
engine has 30 connections (``create_engine``: 10 + 20 overflow) and the gateway authorizer
needs them too:
if sign-ins could hold all 30, a flood of unknown-email sign-ins would queue every other service's
authorization behind them. ``WORKERS + QUEUE_LIMIT`` is therefore kept to at most half the pool.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from identity.local_auth import domain
from identity.local_auth.errors import TooManyAttemptsError

T = TypeVar("T")

WORKERS = max(1, min(4, os.cpu_count() or 1))
QUEUE_LIMIT = 8

_pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="argon2")
_waiting = 0


async def _run(function: Callable[..., T], *args: object) -> T:
    global _waiting
    if _waiting >= WORKERS + QUEUE_LIMIT:
        raise TooManyAttemptsError("Too many attempts. Wait a minute and try again.")
    _waiting += 1
    try:
        return await asyncio.get_running_loop().run_in_executor(_pool, function, *args)
    finally:
        _waiting -= 1


async def hash_password(password: str) -> str:
    return await _run(domain.hash_password, password)


async def verify_password(stored: str, password: str) -> bool:
    return await _run(domain.verify_password, stored, password)


async def burn_verification(password: str) -> None:
    """Spend one verification's time on an unknown account, without holding up the loop."""
    await _run(domain.burn_verification, password)
