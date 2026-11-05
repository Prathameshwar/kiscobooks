"""Bounded non-personal choice projections; Redis never authorizes or validates writes.

READ COMMITTED loaders can observe concurrent commits between queries. Rechecking
the database generation after loading prevents caching that mixed projection. An old
in-flight loader can only fill its old generation, whose keys expire normally.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import TypeVar

from billing_platform.cache import CacheUnavailableError, RedisCache
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from identity.events.reference_cache import pending_changes
from identity.models.reference_cache import ReferenceCacheGeneration

T = TypeVar("T")
VARIANTS = frozenset({"registration", "tenant", "options", "countries", "currencies"})


def namespace(database_url: str) -> str:
    url = make_url(database_url)
    # Credentials are deliberately excluded; credential rotation preserves the namespace.
    source = repr((url.get_backend_name(), url.host, url.port, url.database))
    return "identity:references:" + hashlib.sha256(source.encode()).hexdigest()[:32]


class ReferenceChoiceCache:
    maximum_bytes = 2_000_000

    def __init__(self, cache: RedisCache, *, ttl_seconds: int = 300) -> None:
        if type(ttl_seconds) is not int or not 0 <= ttl_seconds <= 3600:
            raise ValueError("reference cache TTL must be between 0 and 3600 seconds")
        self.cache, self.ttl_seconds = cache, ttl_seconds
        self._fill_lock = asyncio.Lock()

    async def _read(self, key: str, adapter: TypeAdapter[T]) -> T | None:
        try:
            value = await self.cache.get(key)
        except UnicodeError:
            return None
        if value is None or len(value) > self.maximum_bytes:
            return None
        try:
            if len(value.encode("utf-8")) > self.maximum_bytes:
                return None
            parsed = adapter.validate_json(value, strict=True)
            payload = parsed.model_dump() if isinstance(parsed, BaseModel) else parsed
            if isinstance(payload, list) and len(payload) > 1000:
                return None
            if isinstance(payload, dict) and any(
                isinstance(rows, list) and len(rows) > (10000 if name == "states" else 1000)
                for name, rows in payload.items()
            ):
                return None
            return parsed
        except (ValidationError, ValueError, RecursionError):
            return None

    async def resolve(
        self,
        db: AsyncSession,
        variant: str,
        adapter: TypeAdapter[T],
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        if variant not in VARIANTS and not (
            variant.startswith("states:")
            and len(variant) == 9
            and variant[7:].isascii()
            and variant[7:].isalpha()
            and variant[7:].isupper()
        ):
            raise ValueError("unsupported reference projection")
        if self.ttl_seconds == 0 or pending_changes(db.sync_session):
            return await loader()
        statement = select(ReferenceCacheGeneration.token).where(
            ReferenceCacheGeneration.key == "global"
        )
        generation = await db.scalar(statement)
        if generation is None:
            # An installation with no source writes yet has no generation. No request
            # creates database records just to enable a cache.
            return await loader()
        key = f"v1:{variant}:{generation.hex}"
        try:
            hit = await self._read(key, adapter)
        except CacheUnavailableError:
            return await loader()
        if hit is not None:
            return hit
        # One bounded local lock coalesces cold misses without unbounded per-key state.
        async with self._fill_lock:
            try:
                hit = await self._read(key, adapter)
            except CacheUnavailableError:
                return await loader()
            if hit is not None:
                return hit
            value = await loader()
            current = await db.scalar(statement)
            if current != generation or pending_changes(db.sync_session):
                return value
            raw = adapter.dump_json(value)
            if len(raw) <= self.maximum_bytes:
                try:
                    await self.cache.set(key, raw.decode("utf-8"), self.ttl_seconds)
                except CacheUnavailableError:
                    pass
            return value
