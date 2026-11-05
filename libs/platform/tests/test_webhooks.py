from __future__ import annotations

import hashlib
import hmac

import pytest

from billing_platform.errors import PermissionDeniedError
from billing_platform.webhooks import TimestampedHmacVerifier, verify_sha256_hmac


def test_timestamped_signature_and_replay_window() -> None:
    body = b"{}"
    signature = hmac.new(b"secret", b"100." + body, hashlib.sha256).hexdigest()
    TimestampedHmacVerifier(b"secret", clock=lambda: 100).verify(
        body, timestamp="100", signature=signature
    )
    with pytest.raises(PermissionDeniedError):
        TimestampedHmacVerifier(b"secret", clock=lambda: 1000).verify(
            body, timestamp="100", signature=signature
        )


def test_plain_hmac_verifier() -> None:
    body = b"payload"
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    verify_sha256_hmac(body, secret=b"secret", signature=signature)
    with pytest.raises(PermissionDeniedError):
        verify_sha256_hmac(body, secret=b"secret", signature="bad")
