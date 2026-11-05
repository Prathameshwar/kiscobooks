"""Bounded per-process rate guard; a shared gateway supplies the global limit."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class WindowLimiter:
    capacity: int = 4096
    seconds: int = 60
    clock: Callable[[], float] = time.monotonic
    _windows: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False)
    _period: int = field(default=-1, repr=False)

    def allow(self, key: str, *, limit: int) -> bool:
        if not 1 <= limit <= 100_000 or not 1 <= self.seconds <= 3600 or len(key) > 128:
            raise ValueError("invalid rate limit bounds")
        period = int(self.clock()) // self.seconds
        if period != self._period:
            self._windows.clear()
            self._period = period
        value = self._windows.get(key)
        if value is None:
            if len(self._windows) >= self.capacity:
                return False
            count = 0
        else:
            count = value[1]
        if count >= limit:
            return False
        self._windows[key] = (period, count + 1)
        return True
