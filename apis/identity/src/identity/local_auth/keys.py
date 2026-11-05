"""RS256 signing keys for the local provider: generate, encrypt at rest, publish, rotate.

The private half is stored only as AES-256-GCM ciphertext bound to the key id (so a ciphertext
copied onto another row does not decrypt), under a key that arrives from configuration and is
never in the database. The public half is what ``/jwks`` serves; the verifier already refuses a
key set that carries a private member, and so does :meth:`SigningKeys.public_set`.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import secrets
import time
from typing import Any

from billing_platform.crypto import AesGcmCipher
from billing_platform.db.types import utcnow
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import LocalAuthSettings
from identity.models.local_auth import LocalSigningKey

#: How long a decrypted key is kept in memory before it is read (and decrypted) again.
_CACHE_SECONDS = 60
#: The verifier reads at most this many keys (``billing_platform.oidc``), so never publish more.
MAX_PUBLISHED = 8


class SigningKeys:
    def __init__(self, settings: LocalAuthSettings) -> None:
        key = base64.b64decode(settings.key_encryption_key.get_secret_value())
        self._cipher = AesGcmCipher(key)
        self._cached: tuple[float, str, RSAKey] | None = None

    # -- at rest ---------------------------------------------------------------------------

    def _seal(self, kid: str, private: dict[str, Any]) -> str:
        sealed = self._cipher.encrypt(
            json.dumps(private, separators=(",", ":")).encode(),
            nonce=secrets.token_bytes(12),
            associated_data=kid.encode(),
        )
        return base64.b64encode(sealed).decode()

    def _open(self, row: LocalSigningKey) -> RSAKey:
        plain = self._cipher.decrypt(
            base64.b64decode(row.private_jwk_ciphertext), associated_data=row.kid.encode()
        )
        return RSAKey.import_key(json.loads(plain))

    # -- lifecycle -------------------------------------------------------------------------

    async def generate(self, db: AsyncSession) -> LocalSigningKey:
        """Create a key and make it the one that signs. The previous signer keeps verifying."""
        kid = secrets.token_hex(16)
        key = RSAKey.generate_key(2048, parameters={"kid": kid, "use": "sig", "alg": "RS256"})
        for previous in await db.scalars(
            select(LocalSigningKey).where(LocalSigningKey.status == "active")
        ):
            previous.status = "retiring"
            previous.retired_at = utcnow()
        row = LocalSigningKey(
            kid=kid,
            status="active",
            public_jwk=json.dumps(key.as_dict(private=False), separators=(",", ":")),
            private_jwk_ciphertext=self._seal(kid, key.as_dict(private=True)),
        )
        db.add(row)
        await db.flush()
        self._cached = None
        return row

    async def retire_expired(self, db: AsyncSession, *, longest_token: dt.timedelta) -> int:
        """Stop publishing a rotated-out key once every token it signed has expired."""
        cutoff = utcnow() - longest_token
        retired = 0
        for row in await db.scalars(
            select(LocalSigningKey).where(
                LocalSigningKey.status == "retiring", LocalSigningKey.retired_at <= cutoff
            )
        ):
            row.status = "retired"
            retired += 1
        await db.flush()
        return retired

    # -- use -------------------------------------------------------------------------------

    async def signer(self, db: AsyncSession) -> tuple[str, RSAKey]:
        """The newest active key, created on first use."""
        now = time.monotonic()
        if self._cached is not None and now - self._cached[0] < _CACHE_SECONDS:
            return self._cached[1], self._cached[2]
        row = await db.scalar(
            select(LocalSigningKey)
            .where(LocalSigningKey.status == "active")
            .order_by(LocalSigningKey.created_at.desc(), LocalSigningKey.kid)
            .limit(1)
        )
        if row is None:
            row = await self.generate(db)
            # Not cached: this transaction may still roll back, and a cached key that was never
            # committed would sign tokens nobody can verify until the cache expired.
            return row.kid, self._open(row)
        key = self._open(row)
        self._cached = (now, row.kid, key)
        return row.kid, key

    async def public_set(self, db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
        """The JWKS document: active and rotating-out keys, public members only."""
        await self.signer(db)  # a brand-new installation publishes its first key
        rows = (
            await db.scalars(
                select(LocalSigningKey)
                .where(LocalSigningKey.status.in_(("active", "retiring")))
                .order_by(LocalSigningKey.created_at.desc())
                .limit(MAX_PUBLISHED)
            )
        ).all()
        keys: list[dict[str, Any]] = []
        for row in rows:
            public = json.loads(row.public_jwk)
            if "d" in public or public.get("kty") != "RSA":
                continue  # defensive: never publish anything but a public RSA key
            keys.append(public)
        return {"keys": keys}

    def sign(self, kid: str, key: RSAKey, claims: dict[str, Any], *, typ: str) -> str:
        return jwt.encode({"alg": "RS256", "kid": kid, "typ": typ}, claims, key)
