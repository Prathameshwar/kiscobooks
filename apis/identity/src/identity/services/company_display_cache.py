"""Permission-projected company display values cached under immutable source versions.

The endpoint authorizes and resolves current field access before calling this adapter.
Keys therefore include the actor-specific access fingerprint as well as the company
and user row versions. Redis is only an optimization: every failure or untrusted value
falls back to the supplied authoritative loader.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime

from billing_platform.cache import CacheUnavailableError, RedisCache
from pydantic import TypeAdapter
from sqlalchemy.engine import make_url

from identity.schemas.company import DisplayConfig

_LOG = logging.getLogger(__name__)
_FIELD_ADAPTERS = {
    key: TypeAdapter(field.rebuild_annotation())
    for key, field in DisplayConfig.model_fields.items()
}


def namespace(database_url: str) -> str:
    """Database-specific namespace without credentials or other connection secrets."""
    url = make_url(database_url)
    source = repr((url.get_backend_name(), url.host, url.port, url.database))
    return "identity:company-display:" + hashlib.sha256(source.encode()).hexdigest()[:32]


def _version(value: datetime | None) -> str:
    return value.isoformat(timespec="microseconds") if value is not None else "missing"


def display_key(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    company_version: datetime,
    user_version: datetime | None,
    access_fingerprint: str,
) -> str:
    """Bound every isolation/version input into a fixed-size opaque Redis key."""
    source = json.dumps(
        [
            "v1",
            str(tenant_id),
            str(company_id),
            str(user_id),
            _version(company_version),
            _version(user_version),
            access_fingerprint,
        ],
        separators=(",", ":"),
    )
    return "v1:" + hashlib.sha256(source.encode()).hexdigest()


class CompanyDisplayCache:
    """A validated sparse ``DisplayConfig`` projection with bounded telemetry."""

    maximum_bytes = 16_384

    def __init__(self, cache: RedisCache, *, ttl_seconds: int = 300) -> None:
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise ValueError("company display cache TTL must be between 1 and 3600 seconds")
        self.cache = cache
        self.ttl_seconds = ttl_seconds
        self._outcomes: Counter[str] = Counter()

    @property
    def outcomes(self) -> dict[str, int]:
        """Process-local bounded counters; labels never contain tenant or user data."""
        return dict(self._outcomes)

    def _record(self, outcome: str) -> None:
        self._outcomes[outcome] += 1
        _LOG.debug("company display cache outcome=%s", outcome)

    @classmethod
    def _decode(cls, raw: str) -> dict[str, object]:
        if len(raw.encode("utf-8")) > cls.maximum_bytes:
            raise ValueError("cached company display projection is oversized")
        value = json.loads(raw)
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("cached company display projection is not an object")
        if set(value) - set(_FIELD_ADAPTERS):
            raise ValueError("cached company display projection has unknown fields")
        for key, item in value.items():
            _FIELD_ADAPTERS[key].validate_python(item, strict=True)
            if isinstance(item, str):
                item.encode("utf-8")  # JSON escapes must not smuggle unpaired surrogates.
        return value

    async def resolve(
        self,
        key: str,
        loader: Callable[[], Awaitable[dict[str, object]]],
    ) -> dict[str, object]:
        raw: str | None = None
        read_failed = False
        try:
            raw = await self.cache.get(key)
        except (CacheUnavailableError, UnicodeError):
            read_failed = True
            self._record("fallback")
        if raw is not None:
            try:
                value = self._decode(raw)
            except (UnicodeError, ValueError, TypeError, RecursionError):
                self._record("fallback")
            else:
                self._record("hit")
                return value
        elif not read_failed:
            self._record("miss")

        value = await loader()
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        # The authoritative path should already satisfy the response model. Rechecking
        # here prevents a future caller from publishing an incompatible cache value.
        self._decode(encoded)
        # A failed read already proved Redis unavailable. Do not pay a second network
        # timeout attempting to populate it; the next request can probe recovery.
        if not read_failed and len(encoded.encode("utf-8")) <= self.maximum_bytes:
            try:
                await self.cache.set(key, encoded, self.ttl_seconds)
            except CacheUnavailableError:
                self._record("fallback")
            else:
                self._record("fill")
        return value


__all__ = ["CompanyDisplayCache", "display_key", "namespace"]
