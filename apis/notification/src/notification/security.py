"""Sensitive-destination hashing and the shared authenticated field cipher."""

from __future__ import annotations

import hashlib
import hmac

from billing_platform.crypto import AesGcmCipher

__all__ = ["AesGcmCipher", "keyed_destination_hash"]


def keyed_destination_hash(normalized_destination: str, key: bytes) -> bytes:
    return hmac.digest(key, normalized_destination.encode(), hashlib.sha256)
