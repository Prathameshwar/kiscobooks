"""``idempotency_key``: the table behind invariant 2.

A replayed money-mutating request must produce one effect. Two things have to hold
for that, and both are tested here rather than left to the endpoint that will use
them: the key is unique *within* a tenant and *per endpoint*, and one tenant can
never see another's keys — a leaked key is a replayable money mutation.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.platform_models import IdempotencyKey
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from tests.helpers import table_of

_ENDPOINT = "POST /v1/invoices"


def _key(
    tenant_id: uuid.UUID,
    *,
    key_value: str = "client-supplied-1",
    endpoint: str = _ENDPOINT,
    request_hash: str = "a" * 64,
) -> IdempotencyKey:
    return IdempotencyKey(
        id=uuid7(),
        tenant_id=tenant_id,
        key_value=key_value,
        endpoint=endpoint,
        request_hash=request_hash,
        state="in_progress",
        expires_at=utcnow() + dt.timedelta(hours=24),
        attempt_count=0,
    )


async def test_the_same_key_twice_in_one_tenant_is_rejected(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Enforced by the constraint, not by a read-then-write check: two concurrent
    replays would both pass the read."""
    with tenant_scope(tenant_a):
        session.add(_key(tenant_a))
        await session.commit()

        session.add(_key(tenant_a))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        rows = (await session.execute(select(IdempotencyKey))).scalars().all()
    assert len(rows) == 1


async def test_the_same_key_on_a_different_endpoint_is_allowed(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """``endpoint`` is in the key so a client reusing one key across two calls does
    not have the second one silently answered with the first one's response."""
    with tenant_scope(tenant_a):
        session.add(_key(tenant_a, endpoint="POST /v1/invoices"))
        session.add(_key(tenant_a, endpoint="POST /v1/payments"))
        await session.commit()

        rows = (await session.execute(select(IdempotencyKey))).scalars().all()
    assert len(rows) == 2


async def test_two_tenants_may_use_the_same_key_value(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Clients pick their own key values; a collision across tenants is expected and
    must not make one tenant's request fail because of another's."""
    with tenant_scope(tenant_a):
        session.add(_key(tenant_a))
        await session.commit()
    with tenant_scope(tenant_b):
        session.add(_key(tenant_b))
        await session.commit()

        rows = (await session.execute(select(IdempotencyKey))).scalars().all()
    assert [row.tenant_id for row in rows] == [tenant_b]


async def test_one_tenants_keys_are_invisible_to_another(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The isolation test every table gets (CLAUDE.md §7). Highest stakes on this
    one: a readable key from another tenant is a replayable money mutation."""
    with tenant_scope(tenant_a):
        session.add(_key(tenant_a, key_value="tenant-a-key"))
        await session.commit()

    with tenant_scope(tenant_b):
        rows = (await session.execute(select(IdempotencyKey))).scalars().all()
    assert rows == []

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(IdempotencyKey))).scalars().all()
    assert [row.key_value for row in rows] == ["tenant-a-key"]


def test_request_hash_is_not_nullable() -> None:
    """A key reused with a *different* body must return 422, never a replay of the
    first response. Nullable, there would be nothing to compare against, and every
    row written before the column was added would be unverifiable."""
    column = table_of(IdempotencyKey).columns["request_hash"]
    assert column.nullable is False
    # Wide enough for a hex SHA-256 and no wider, so a truncated hash cannot be
    # stored and later compare equal to a full one.
    column_type = column.type
    assert isinstance(column_type, String)
    assert column_type.length == 64


def test_tenant_id_leads_the_unique_constraint() -> None:
    """§1.7: the session filter puts ``tenant_id`` in every query, so an index that
    does not lead with it cannot be used by the query that matters."""
    unique = [c for c in table_of(IdempotencyKey).constraints if isinstance(c, UniqueConstraint)]
    assert len(unique) == 1
    assert [c.name for c in unique[0].columns] == ["tenant_id", "endpoint", "key_value"]
