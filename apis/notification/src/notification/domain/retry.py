from __future__ import annotations

import hashlib
import uuid


def backoff_seconds(attempt: int, *, initial: int, maximum: int, stable_key: uuid.UUID) -> int:
    if attempt < 1 or initial < 1 or maximum < initial:
        raise ValueError("invalid retry policy")
    # `1 << n` keeps this int-typed; `2 ** n` is typed Any (a negative exponent would
    # yield float), which would leak Any through the return.
    ceiling = min(maximum, initial * (1 << (attempt - 1)))
    jitter = int.from_bytes(
        hashlib.sha256(stable_key.bytes + attempt.to_bytes(2, "big")).digest()[:4], "big"
    )
    return max(1, ceiling // 2 + jitter % max(1, ceiling // 2 + 1))
