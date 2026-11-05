"""Authenticated field encryption shared by owning services; keys come from a secret manager."""

from __future__ import annotations

from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class AesGcmCipher:
    """AES-256-GCM primitive; production keys are resolved from a secret manager."""

    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")

    def encrypt(self, plaintext: bytes, *, nonce: bytes, associated_data: bytes) -> bytes:
        if len(nonce) != 12:
            raise ValueError("AES-GCM nonce must be 12 bytes")
        return nonce + AESGCM(self.key).encrypt(nonce, plaintext, associated_data)

    def decrypt(self, ciphertext: bytes, *, associated_data: bytes) -> bytes:
        if len(ciphertext) < 28:
            raise ValueError("ciphertext is truncated")
        return AESGCM(self.key).decrypt(ciphertext[:12], ciphertext[12:], associated_data)
