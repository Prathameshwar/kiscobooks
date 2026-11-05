"""Bounded service polling without hiding cancellation or logging connection contents."""

import asyncio
import logging
from collections.abc import Awaitable, Callable


async def repeat(operation: Callable[[], Awaitable[None]], *, interval: float) -> None:
    while True:
        try:
            await operation()
        except Exception as exc:
            logging.getLogger(__name__).warning("Worker poll will retry: %s", type(exc).__name__)
        await asyncio.sleep(interval)


async def repeat_independently(
    operations: tuple[Callable[[], Awaitable[None]], ...], *, parallelism: int, interval: float
) -> None:
    """Each scope polls independently; slow scopes occupy only their bounded worker slots."""
    if parallelism < 1 or interval <= 0 or not operations:
        raise ValueError("independent polling requires operations and positive bounds")
    slots = asyncio.Semaphore(parallelism)

    async def bounded(operation: Callable[[], Awaitable[None]]) -> None:
        async with slots:
            await operation()

    async with asyncio.TaskGroup() as group:
        for operation in operations:

            async def step(current: Callable[[], Awaitable[None]] = operation) -> None:
                await bounded(current)

            group.create_task(repeat(step, interval=interval))
