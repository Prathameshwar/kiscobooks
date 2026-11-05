from __future__ import annotations

import secrets

import pytest
from cryptography.exceptions import InvalidTag

from billing_platform.audit_context import audit_actor, resolve_actor
from billing_platform.crypto import AesGcmCipher
from billing_platform.ids import uuid7


@pytest.mark.parametrize("payload", [b"", b"private data"])
def test_encryption_roundtrip_and_authentication(payload):
    cipher = AesGcmCipher(secrets.token_bytes(32))
    encrypted = cipher.encrypt(
        payload, nonce=secrets.token_bytes(12), associated_data=b"tenant/company/row"
    )
    assert cipher.decrypt(encrypted, associated_data=b"tenant/company/row") == payload
    with pytest.raises(InvalidTag):
        cipher.decrypt(encrypted, associated_data=b"different/tenant")
    with pytest.raises(InvalidTag):
        cipher.decrypt(
            encrypted[:-1] + bytes([encrypted[-1] ^ 1]), associated_data=b"tenant/company/row"
        )
    assert cipher.key.hex() not in repr(cipher)
    with pytest.raises(ValueError):
        cipher.encrypt(payload, nonce=b"short", associated_data=b"scope")
    with pytest.raises(ValueError):
        cipher.decrypt(b"truncated", associated_data=b"scope")
    with pytest.raises(ValueError):
        AesGcmCipher(b"short")


def test_nested_audit_attribution_restores_even_after_exception():
    real, effective, other = uuid7(), uuid7(), uuid7()
    assert resolve_actor(effective, None) == (effective, None)
    with audit_actor(real, effective):
        assert resolve_actor(effective, None) == (real, effective)
        assert resolve_actor(other, None) == (other, None)
        with pytest.raises(RuntimeError), audit_actor(None, effective):
            assert resolve_actor(effective, None) == (effective, None)
            raise RuntimeError("test rollback")
        assert resolve_actor(effective, None) == (real, effective)
    assert resolve_actor(effective, None) == (effective, None)


def test_correlation_rejects_untrusted_text_and_resets_after_nested_failures():
    import pytest

    from billing_platform.audit_context import audit_request, correlation

    assert correlation() == (None, None)
    with audit_request("a" * 32, "00000000-0000-0000-0000-000000000001"):
        assert correlation()[0] == "a" * 32
        with pytest.raises(ValueError), audit_request("private@example.test", "secret"):
            assert correlation() == (None, None)
            raise ValueError("test rollback")
        assert correlation()[0] == "a" * 32
    assert correlation() == (None, None)
