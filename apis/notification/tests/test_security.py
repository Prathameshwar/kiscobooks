from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from notification.security import AesGcmCipher, keyed_destination_hash


def test_sensitive_data_is_authenticated_and_hash_is_keyed() -> None:
    cipher = AesGcmCipher(b"k" * 32)
    encrypted = cipher.encrypt(b"secret", nonce=b"n" * 12, associated_data=b"tenant")
    assert cipher.decrypt(encrypted, associated_data=b"tenant") == b"secret"
    with pytest.raises(InvalidTag):
        cipher.decrypt(encrypted, associated_data=b"other")
    assert keyed_destination_hash("a@example.com", b"a") != keyed_destination_hash(
        "a@example.com", b"b"
    )
