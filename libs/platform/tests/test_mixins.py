"""Mixin behaviour.

The mixins are the reason 35 tables do not restate 300 columns, so a change in
one of them lands everywhere at once. These tests pin the parts a table author
relies on without re-reading the mixin.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.base import Base
from billing_platform.db.mixins import (
    AuditMixin,
    DeactivableMixin,
    EffectiveMixin,
    IdMixin,
    StatusMixin,
    TenantMixin,
)
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.db.types import Uuid7
from tests.helpers import table_of
from tests.models import SharedThing, TenantThing


async def test_id_is_generated_as_uuid7_when_not_supplied(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Callers never pass an id. v7 and not v4 so the PK clusters on InnoDB."""
    with unfiltered():
        row = TenantThing(tenant_id=tenant_a, name="x")
        session.add(row)
        await session.commit()

    assert isinstance(row.id, uuid.UUID)
    assert row.id.version == 7


def test_id_column_is_binary_16_and_primary_key() -> None:
    col = table_of(TenantThing).c.id
    assert isinstance(col.type, Uuid7)
    assert col.primary_key is True


def test_tenant_id_is_not_null_indexed_and_carries_no_foreign_key() -> None:
    table = table_of(TenantThing)
    col = table.c.tenant_id
    assert col.nullable is False
    assert col.foreign_keys == set(), "tenant_id deliberately carries no FK"
    assert any("tenant_id" in {c.name for c in ix.columns} for ix in table.indexes)


def test_tenant_shared_defaults_to_false_and_is_opt_in() -> None:
    assert TenantThing.__tenant_shared__ is False
    assert SharedThing.__tenant_shared__ is True


def test_audit_by_columns_are_nullable_and_carry_no_foreign_key() -> None:
    """System and migration writes have no actor, and the FK direction is taken
    by ``user.default_company_id``."""
    for name in ("created_by", "updated_by"):
        col = table_of(TenantThing).c[name]
        assert col.nullable is True
        assert col.foreign_keys == set()


async def test_created_at_and_updated_at_are_populated_on_insert(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with unfiltered():
        session.add(TenantThing(tenant_id=tenant_a, name="x"))
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(TenantThing))).scalar_one()

    assert isinstance(row.created_at, dt.datetime)
    assert isinstance(row.updated_at, dt.datetime)
    assert row.created_by is None


async def test_updated_at_moves_on_update_and_created_at_does_not(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with unfiltered():
        row = TenantThing(tenant_id=tenant_a, name="before")
        session.add(row)
        await session.commit()
        first_created, first_updated = row.created_at, row.updated_at

        row.name = "after"
        await session.commit()

    assert row.created_at == first_created
    assert row.updated_at >= first_updated


class _Lifecycle(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    __tablename__ = "mixin_lifecycle_probe"
    label: Mapped[str] = mapped_column(String(20), nullable=False)


class _Dated(IdMixin, TenantMixin, EffectiveMixin, Base):
    __tablename__ = "mixin_dated_probe"
    label: Mapped[str] = mapped_column(String(20), nullable=False)


class _Stateful(IdMixin, TenantMixin, StatusMixin, Base):
    __tablename__ = "mixin_status_probe"
    label: Mapped[str] = mapped_column(String(20), nullable=False)


async def test_deactivable_defaults_to_active(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    col = table_of(_Lifecycle).c.is_active
    assert isinstance(col.type, Boolean)
    assert col.nullable is False

    with unfiltered():
        row = _Lifecycle(tenant_id=tenant_a, label="x")
        session.add(row)
        await session.commit()

    assert row.is_active is True
    assert row.deactivated_at is None
    assert row.deactivated_by is None


def test_effective_uses_dates_never_datetimes() -> None:
    """Rule 4.12: anything affecting a computed amount is dated, not flagged."""
    table = table_of(_Dated)
    assert isinstance(table.c.valid_from.type, Date)
    assert isinstance(table.c.valid_to.type, Date)
    assert table.c.valid_from.nullable is False
    assert table.c.valid_to.nullable is True


def test_one_lifecycle_mechanism_per_entity() -> None:
    """``status`` or ``is_active`` or dates — never two on one table (rule 4.12)."""
    for model in (_Lifecycle, _Dated, _Stateful):
        columns = set(table_of(model).c.keys())
        mechanisms = [
            "is_active" in columns,
            "status" in columns,
            "valid_from" in columns,
        ]
        assert sum(mechanisms) == 1, f"{model.__tablename__} has {sum(mechanisms)}"
