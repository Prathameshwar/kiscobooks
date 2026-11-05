"""The ambient tenant for the current task.

A ``ContextVar``, so it is per-task under asyncio rather than per-thread — two
concurrent requests in one worker must never see each other's tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)

# Set only by deliberate, audited operations: seeding, migrations, and the
# platform-admin paths that are allowed to cross tenants. Never set from a
# request handler.
_filter_disabled: ContextVar[bool] = ContextVar("tenant_filter_disabled", default=False)


class TenantContextError(RuntimeError):
    """Raised when a tenant-scoped query runs with no tenant in context.

    Deliberately an error rather than an empty result or an unfiltered one.
    Returning everything would be a cross-tenant breach; returning nothing would
    hide the bug until someone reported missing data.
    """


class UnfilterableStatementError(TenantContextError):
    """A statement touches a tenant table in a shape the filter cannot reach.

    ``with_loader_criteria`` attaches to the ORM entities in a statement's columns
    clause. A statement with none — ``select(func.count()).select_from(Model)`` is
    the one that occurs in practice — silently runs across every tenant. It is a
    cross-tenant read, so it raises rather than being quietly allowed.
    """


#: Opaque handle from ``set_current_tenant``, to be handed back verbatim.
TenantToken = Token[uuid.UUID | None]


def set_current_tenant(tenant_id: uuid.UUID | None) -> TenantToken:
    """Set the ambient tenant. Returns a token for ``reset_current_tenant``."""
    return _current_tenant.set(tenant_id)


def reset_current_tenant(token: TenantToken) -> None:
    _current_tenant.reset(token)


def get_current_tenant() -> uuid.UUID | None:
    return _current_tenant.get()


def require_current_tenant() -> uuid.UUID:
    tenant_id = _current_tenant.get()
    if tenant_id is None:
        raise TenantContextError(
            "no tenant in context; a tenant-scoped query cannot run unfiltered"
        )
    return tenant_id


def is_filter_disabled() -> bool:
    return _filter_disabled.get()


@contextmanager
def tenant_scope(tenant_id: uuid.UUID) -> Iterator[None]:
    """Run a block with ``tenant_id`` as the ambient tenant."""
    token = _current_tenant.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant.reset(token)


@contextmanager
def unfiltered() -> Iterator[None]:
    """Disable the tenant filter for a block.

    For seeds, migrations, and audited cross-tenant platform operations only.
    Every use in service code needs a comment saying why, and a platform-admin
    use must emit a ``security``-category audit event (CLAUDE.md §5.6).
    """
    token = _filter_disabled.set(True)
    try:
        yield
    finally:
        _filter_disabled.reset(token)
