"""Bounded OIDC access-token verification (Authentik or the local provider).

Identity owns subject/grant resolution.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from billing_platform.errors import AuthenticationRequiredError, PlatformError

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class IdentityProviderUnavailableError(PlatformError):
    status_code = 503
    code = "identity_provider_unavailable"


class ProviderIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    provider: str = Field(min_length=1, max_length=40)
    subject: str = Field(min_length=1, max_length=255)


class VerifiedClaims(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)
    iss: str
    aud: str | list[str]
    sub: str = Field(min_length=1, max_length=64)
    exp: StrictInt
    iat: StrictInt
    nbf: StrictInt | None = None
    auth_time: StrictInt | None = None
    org_id: uuid.UUID | None = None
    azp: str | None = None
    scope: str = Field(max_length=4096)
    email: str | None = Field(default=None, max_length=320)
    email_verified: StrictBool = False
    linked_identities: tuple[ProviderIdentity, ...] = Field(default=(), max_length=16)


@dataclass(frozen=True, slots=True)
class OidcConfig:
    issuer: str
    audience: str
    jwks_url: str
    api_scope: str = "billing.api"
    cache_seconds: int = 300
    max_token_seconds: int = 300

    def __post_init__(self) -> None:
        for url in (self.issuer, self.jwks_url):
            parsed = urlsplit(url)
            # HTTPS, or plain HTTP to a loopback host only: that traffic never leaves the machine,
            # so a development install needs no certificate. Exact names — never a suffix or
            # prefix match, so `localhost.evil.example` and `127.0.0.1.evil.example` stay refused.
            secure = parsed.scheme == "https" or (
                parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS
            )
            if (
                not secure
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("OIDC URLs must be HTTPS endpoints (plain HTTP only for loopback)")
        if not self.audience or not self.api_scope or " " in self.api_scope:
            raise ValueError("OIDC audience and one API scope are required")
        if not 5 <= self.cache_seconds <= 300 or not 60 <= self.max_token_seconds <= 900:
            raise ValueError("OIDC key cache and access-token lifetime must be bounded")


def _header(token: str) -> dict[str, Any]:
    if not 1 <= len(token) <= 16_384 or token.count(".") != 2:
        raise ValueError("invalid token size")
    encoded = token.split(".", 1)[0]
    raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    result: Any = json.loads(raw)
    if (
        not isinstance(result, dict)
        or result.get("alg") != "RS256"
        or not isinstance(result.get("kid"), str)
        or not 1 <= len(result["kid"]) <= 200
        or any(key in result for key in ("jku", "jwk", "x5u", "crit"))
    ):
        raise ValueError("invalid token header")
    return result


class AccessTokenVerifier:
    def __init__(self, config: OidcConfig, client: httpx.AsyncClient) -> None:
        self.config, self.client = config, client
        self.keys: KeySet | None = None
        self.kids: frozenset[str] = frozenset()
        self.fetched_at = 0.0
        self.last_attempt = 0.0
        self.lock = asyncio.Lock()

    async def _keys(self, kid: str) -> KeySet:
        async with self.lock:
            moment = time.monotonic()
            fresh = self.keys is not None and moment - self.fetched_at < self.config.cache_seconds
            if fresh and kid in self.kids:
                assert self.keys is not None
                return self.keys
            # Unknown IDs and outages cannot trigger an unbounded provider request flood.
            if moment - self.last_attempt < 5:
                if fresh:
                    raise AuthenticationRequiredError("invalid access token")
                raise IdentityProviderUnavailableError("identity signing keys are unavailable")
            self.last_attempt = moment
            try:
                async with self.client.stream(
                    "GET", self.config.jwks_url, timeout=5, follow_redirects=False
                ) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 131_072:
                            raise ValueError("oversized signing key set")
                document = json.loads(raw)
                if not isinstance(document, dict):
                    raise ValueError("invalid signing key document")
                keys = document.get("keys")
                if not isinstance(keys, list) or not 1 <= len(keys) <= 16:
                    raise ValueError("invalid signing key set")
                accepted = [
                    key
                    for key in keys
                    if isinstance(key, dict)
                    and key.get("kty") == "RSA"
                    and key.get("use", "sig") == "sig"
                    and key.get("alg", "RS256") == "RS256"
                ]
                kids = [key.get("kid") for key in accepted]
                if (
                    not kids
                    or any(not isinstance(value, str) or not value for value in kids)
                    or len(set(kids)) != len(kids)
                    or any("d" in key for key in accepted)
                ):
                    raise ValueError("invalid public signing keys")
                self.keys = KeySet.import_key_set({"keys": accepted})
                self.kids = frozenset(str(kid) for kid in kids)
                self.fetched_at = moment
            except (httpx.HTTPError, ValueError, TypeError, JoseError) as exc:
                raise IdentityProviderUnavailableError(
                    "identity signing keys are unavailable"
                ) from exc
            if kid not in self.kids:
                raise AuthenticationRequiredError("invalid access token")
            return self.keys

    async def verify(self, token: str) -> VerifiedClaims:
        try:
            header = _header(token)
            keys = await self._keys(header["kid"])
            decoded = jwt.decode(token, keys, algorithms=["RS256"])
            claims = VerifiedClaims.model_validate(decoded.claims)
            now = int(time.time())
            audiences = [claims.aud] if isinstance(claims.aud, str) else claims.aud
            if (
                claims.iss != self.config.issuer
                or self.config.audience not in audiences
                or (len(audiences) > 1 and claims.azp != self.config.audience)
                or (claims.azp is not None and claims.azp != self.config.audience)
                or self.config.api_scope not in claims.scope.split()
                or claims.exp <= now
                or claims.iat > now + 30
                or claims.exp <= claims.iat
                or claims.exp - claims.iat > self.config.max_token_seconds
                or (claims.nbf is not None and claims.nbf > now + 30)
                or (claims.auth_time is not None and claims.auth_time > now + 30)
            ):
                raise ValueError("invalid access-token claims")
            return claims
        except (ValueError, TypeError, KeyError, JoseError, ValidationError) as exc:
            raise AuthenticationRequiredError("invalid or expired access token") from exc
