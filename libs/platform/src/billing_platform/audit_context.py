"""Request-scoped real/effective audit attribution, reset even when a request fails."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_attribution: ContextVar[tuple[uuid.UUID, uuid.UUID] | None] = ContextVar(
    "audit_attribution", default=None
)
_correlation: ContextVar[tuple[str | None, str | None]] = ContextVar(
    "audit_correlation", default=(None, None)
)


@contextmanager
def audit_request(trace_id: str | None, request_id: str | None = None) -> Iterator[None]:
    """Bounded opaque correlation only; never retain arbitrary header text."""
    trace = trace_id if trace_id and re.fullmatch(r"[0-9a-fA-F]{16,32}", trace_id) else None
    request = request_id if request_id and re.fullmatch(r"[0-9a-fA-F-]{36}", request_id) else None
    token = _correlation.set((trace, request))
    try:
        yield
    finally:
        _correlation.reset(token)


def correlation() -> tuple[str | None, str | None]:
    return _correlation.get()


@contextmanager
def audit_actor(real_user_id: uuid.UUID | None, effective_user_id: uuid.UUID) -> Iterator[None]:
    token = _attribution.set(
        (real_user_id, effective_user_id) if real_user_id is not None else None
    )
    try:
        yield
    finally:
        _attribution.reset(token)


def resolve_actor(
    actor_user_id: uuid.UUID | None, on_behalf_of_user_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    context = _attribution.get()
    if context is not None and actor_user_id == context[1]:
        return context
    return actor_user_id, on_behalf_of_user_id
