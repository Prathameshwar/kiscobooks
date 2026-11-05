"""The ambient tenant primitive.

It is a ``ContextVar`` and not a module global so two concurrent requests in one
worker cannot see each other's tenant. ``test_concurrent_tasks_do_not_leak``
is the only test that proves that, and it is the reason for the choice.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db.session import SKIP_TENANT_FILTER
from billing_platform.db.tenant_context import (
    TenantContextError,
    get_current_tenant,
    is_filter_disabled,
    require_current_tenant,
    reset_current_tenant,
    set_current_tenant,
    tenant_scope,
    unfiltered,
)
from billing_platform.ids import uuid7
from tests.models import TenantThing


def test_no_tenant_by_default() -> None:
    assert get_current_tenant() is None
    assert is_filter_disabled() is False


def test_set_and_reset_restores_the_previous_value() -> None:
    outer, inner = uuid7(), uuid7()
    outer_token = set_current_tenant(outer)
    inner_token = set_current_tenant(inner)
    assert get_current_tenant() == inner
    reset_current_tenant(inner_token)
    assert get_current_tenant() == outer
    reset_current_tenant(outer_token)
    assert get_current_tenant() is None


def test_tenant_scope_restores_on_exception() -> None:
    with pytest.raises(RuntimeError, match="boom"), tenant_scope(uuid7()):
        raise RuntimeError("boom")
    assert get_current_tenant() is None


def test_unfiltered_restores_on_exception() -> None:
    """A leaked disabled filter would silently unscope every later query in the
    worker, so the restore path is tested rather than assumed."""
    with pytest.raises(RuntimeError, match="boom"), unfiltered():
        raise RuntimeError("boom")
    assert is_filter_disabled() is False


def test_nested_scopes_restore_the_outer_tenant() -> None:
    outer, inner = uuid7(), uuid7()
    with tenant_scope(outer):
        with tenant_scope(inner):
            assert get_current_tenant() == inner
        assert get_current_tenant() == outer


def test_require_current_tenant_raises_rather_than_returning_none() -> None:
    with pytest.raises(TenantContextError):
        require_current_tenant()


def test_require_current_tenant_returns_the_value() -> None:
    tenant = uuid7()
    with tenant_scope(tenant):
        assert require_current_tenant() == tenant


async def test_concurrent_tasks_do_not_leak_each_others_tenant() -> None:
    """Two requests in one worker. A module global would fail this."""
    seen: dict[str, uuid.UUID | None] = {}
    a, b = uuid7(), uuid7()

    async def work(name: str, tenant: uuid.UUID, delay: float) -> None:
        with tenant_scope(tenant):
            await asyncio.sleep(delay)
            seen[name] = get_current_tenant()

    await asyncio.gather(work("a", a, 0.02), work("b", b, 0.0))

    assert seen == {"a": a, "b": b}
    assert get_current_tenant() is None


async def test_skip_tenant_filter_execution_option_bypasses_the_filter(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The per-statement escape hatch. ``unfiltered()`` is preferred because it
    is greppable, but the option is what makes a single query auditable in review."""
    async with factory() as session:
        with unfiltered():
            session.add_all(
                [
                    TenantThing(tenant_id=tenant_a, name="a-one"),
                    TenantThing(tenant_id=tenant_b, name="b-one"),
                ]
            )
            await session.commit()

    stmt = select(TenantThing).execution_options(**{SKIP_TENANT_FILTER: True})

    async with factory() as session:
        rows = (await session.execute(stmt)).scalars().all()

    assert len(rows) == 2
