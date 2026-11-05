"""Provider-callback verification mechanisms."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass

from billing_platform.errors import PermissionDeniedError, ValidationFailedError


@dataclass(frozen=True, slots=True)
class TimestampedHmacVerifier:
    secret: bytes
    tolerance_seconds: int = 300
    clock: Callable[[], float] = time.time

    def verify(self, body: bytes, *, timestamp: str, signature: str) -> None:
        try:
            observed = int(timestamp)
        except ValueError as exc:
            raise ValidationFailedError("invalid callback timestamp") from exc
        if abs(int(self.clock()) - observed) > self.tolerance_seconds:
            raise PermissionDeniedError("callback timestamp outside the accepted window")
        expected = hmac.new(
            self.secret, timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
        supplied = signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, supplied):
            raise PermissionDeniedError("invalid callback signature")


def verify_sha256_hmac(body: bytes, *, secret: bytes, signature: str) -> None:
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
        raise PermissionDeniedError("invalid callback signature")
