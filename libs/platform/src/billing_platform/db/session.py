"""Async engine, session factory, and the session-level tenant filter.

**The filter is registered here, once, for every model carrying ``TenantMixin``.**
It is deliberately not per-query discipline: one forgotten ``WHERE`` is a
cross-tenant breach (CLAUDE.md §5.3, rule 4.9).

``SelfTenantMixin`` is the second, narrower case: ``tenant`` has no ``tenant_id``
because its own ``id`` is one, and it is filtered on that column instead. Both
read the same ambient tenant, so there is one thing to set and one thing to
bypass — not two isolation mechanisms.

**The filter has one shape it cannot reach, and that shape is refused rather than
allowed.** ``with_loader_criteria`` attaches to the ORM entities in a statement's
columns clause; ``select(func.count()).select_from(Invoice)`` has none, so the
criteria is dropped and the count comes back across every tenant. It is an easy
thing to write by accident — every paginated list endpoint needs a total — so it
raises ``UnfilterableStatementError`` with the fix in the message. Joins and
``EXISTS`` subqueries *are* reached and are unaffected.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import ClauseElement, Table, event, or_
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.sql.util import find_tables

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.base import Base
from billing_platform.db.mixins import SelfTenantMixin, TenantMixin
from billing_platform.db.tenant_context import (
    TenantContextError,
    UnfilterableStatementError,
    get_current_tenant,
    is_filter_disabled,
)

#: Execution option to skip the filter for a single statement. Prefer the
#: ``unfiltered()`` context manager, which is greppable.
SKIP_TENANT_FILTER = "skip_tenant_filter"


def database_url(service: str) -> str:
    """``<SERVICE>_DATABASE_URL`` from the environment.

    Never a default and never a value in a file: a URL in the repo is a credential
    in the repo (CLAUDE.md §5.9). The error names the variable and never echoes a
    value, because these URLs contain a password (§5.11).

    Here rather than in one seed's module because every seed and every service entry
    point needs exactly this, and a second copy is a second place for the "no
    default" rule to be relaxed (CLAUDE.md §3).
    """
    variable = f"{service.upper()}_DATABASE_URL"
    url = os.environ.get(variable)
    if not url:
        raise SystemExit(f"{variable} is not set; the seed reads the database URL from it")
    return url


def create_engine(url: str, *, echo: bool = False, pool_size: int = 10) -> AsyncEngine:
    """Create the service engine.

    ``READ COMMITTED`` per rule 4.2: it makes ``SELECT ... FOR UPDATE`` number
    allocation safe without gap locks.
    """
    kwargs: dict[str, Any] = {
        "echo": echo,
        "pool_pre_ping": True,
        "future": True,
    }
    if not url.startswith("sqlite"):
        kwargs["isolation_level"] = "READ COMMITTED"
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = pool_size * 2
    return create_async_engine(url, **kwargs)


def create_session_factory(
    engine: AsyncEngine, *, guarded: bool = False
) -> async_sessionmaker[AsyncSession]:
    """Opt into strict request/worker guards without changing legacy seed adapters."""
    from billing_platform.db.guarded import GuardedSession

    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=GuardedSession if guarded else Session,
        expire_on_commit=False,
        autoflush=False,
    )


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(state: ORMExecuteState) -> None:
    """Append ``tenant_id`` criteria to every ORM SELECT touching a tenant table.

    Registered on ``Session`` (the sync class ``AsyncSession`` proxies), so it
    applies to every session in the process — including ones a service creates
    itself. There is no way to obtain an unfiltered session by accident.
    """
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if state.execution_options.get(SKIP_TENANT_FILTER, False) or is_filter_disabled():
        return

    if not _touches_a_tenant_table(state):
        return

    tenant_id = get_current_tenant()
    if tenant_id is None:
        raise TenantContextError(
            "no tenant in context; a tenant-scoped query cannot run unfiltered. "
            "Use tenant_scope(...) for request work, or unfiltered() for a "
            "deliberate, audited cross-tenant operation."
        )

    _require_a_reachable_entity(state)

    # `tenant_id` is closed over, which SQLAlchemy converts to a bound parameter,
    # so the compiled statement is reused across tenants while the value is not.
    # test_two_tenants_sequentially_are_not_cached proves that.
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: _criteria(cls, tenant_id),
            include_aliases=True,
        ),
        # `tenant` itself: its primary key *is* the tenant id, so the same ambient
        # value filters it on `id`. Registered unconditionally — a criteria for a
        # mixin no entity in the statement inherits is a no-op.
        with_loader_criteria(
            SelfTenantMixin,
            lambda cls: cls.id == tenant_id,
            include_aliases=True,
        ),
    )


def _require_a_reachable_entity(state: ORMExecuteState) -> None:
    """Refuse a statement the criteria provably cannot reach.

    ``with_loader_criteria`` attaches to the ORM entities in the columns clause and
    to every occurrence of them elsewhere, joins included. With **no** entity in the
    columns clause there is nothing to attach to, and the criteria is dropped
    without complaint: ``select(func.count()).select_from(Invoice)`` returns the row
    count of every tenant.

    That is a cross-tenant read, so it raises. The fix is to name the column —
    ``select(func.count(Invoice.id))`` — which restores an entity and filters
    correctly, joins included.
    """
    # A statement shape with no `column_descriptions` at all — `from_statement()`
    # wrapping raw SQL, for instance — is refused for the same reason: what cannot
    # be inspected cannot be proven filtered, and the safe default is to deny.
    descriptions = getattr(state.statement, "column_descriptions", [])
    if any(description.get("entity") is not None for description in descriptions):
        return
    raise UnfilterableStatementError(
        "this statement touches a tenant-scoped table but has no ORM entity in its "
        "columns clause, so the tenant filter cannot attach to it and the query "
        "would run across every tenant. Name the column instead: "
        "select(func.count(Model.id)) rather than "
        "select(func.count()).select_from(Model). For a deliberate cross-tenant "
        "read, use unfiltered()."
    )


def _criteria(cls: Any, tenant_id: uuid.UUID) -> Any:
    """Per-class criteria. Evaluated once per mapped class and cached.

    ``or_`` of two equality tests rather than ``IN (tenant, SCOPE_ALL)``: inside
    a lambda-tracked criteria, SQLAlchemy wraps each closure variable in a
    ``PyWrapper`` to derive bound parameters, and a wrapper inside a list literal
    reaches the type's bind processor unresolved. Equality is the tracked path.
    """
    if getattr(cls, "__tenant_shared__", False):
        # `role` and `role_permission`: system roles carry tenant_id == SCOPE_ALL
        # and belong to every tenant. Filtering on equality alone hides all of them.
        return or_(cls.tenant_id == tenant_id, cls.tenant_id == SCOPE_ALL)
    return cls.tenant_id == tenant_id


#: Tenant-scoped table names, cached and keyed on how many mappers exist. A
#: service registers its models at import time, so the count only changes while the
#: process is starting up — and keying on it means a model imported late is picked
#: up rather than missed for the life of the process.
_TENANT_TABLE_CACHE: dict[int, frozenset[str]] = {}


def _tenant_scoped_tables() -> frozenset[str]:
    mappers = Base.registry.mappers
    cached = _TENANT_TABLE_CACHE.get(len(mappers))
    if cached is None:
        cached = frozenset(
            mapper.local_table.name
            for mapper in mappers
            if issubclass(mapper.class_, TenantMixin | SelfTenantMixin)
            and isinstance(mapper.local_table, Table)
        )
        _TENANT_TABLE_CACHE[len(mappers)] = cached
    return cached


def _touches_a_tenant_table(state: ORMExecuteState) -> bool:
    """Whether this statement reads a table under the filter, in any shape.

    Two tiers. The mapper check is cheap and covers the overwhelming majority —
    anything with an ORM entity, joins and subqueries included. It is not
    sufficient: ``select(func.count()).select_from(Invoice)`` registers no mapper at
    all, which is exactly why that shape used to run across every tenant in
    silence. Catching it needs a walk of the statement's FROM clauses, so that walk
    only happens for statements the first tier did not already claim.
    """
    for desc in state.all_mappers:
        if issubclass(desc.class_, TenantMixin | SelfTenantMixin):
            return True

    # `state.statement` is typed as the broader `Executable`; on a SELECT it is
    # always a clause element, and `is_select` was checked by the caller.
    statement = cast(ClauseElement, state.statement)
    tables = {
        table.name
        for table in find_tables(
            statement, include_joins=True, include_selects=True, include_aliases=True
        )
        if isinstance(table, Table)
    }
    return bool(tables & _tenant_scoped_tables())


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session, committing on success and rolling back on failure."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
