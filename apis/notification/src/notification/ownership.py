"""Notification space policy over the shared partition mechanism."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from billing_platform.db.partition import PartitionedSession, install_partition_guard
from billing_platform.db.tenant_context import get_current_tenant
from billing_platform.db.types import Uuid7
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

_space: ContextVar[uuid.UUID | None] = ContextVar("notification_space", default=None)


def current_space() -> uuid.UUID | None:
    return _space.get() or get_current_tenant()


@contextmanager
def space_scope(space_id: uuid.UUID) -> Iterator[None]:
    token = _space.set(space_id)
    try:
        yield
    finally:
        _space.reset(token)


class SpaceMixin:
    space_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


install_partition_guard(SpaceMixin, column="space_id", resolve=current_space)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        sync_session_class=PartitionedSession,
        expire_on_commit=False,
        autoflush=False,
    )
