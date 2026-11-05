"""Throwaway models used only to exercise the mixins and the tenant filter."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CHAR, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db.base import Base
from billing_platform.db.mixins import AuditMixin, IdMixin, SelfTenantMixin, TenantMixin
from billing_platform.db.types import Money, Quantity, Uuid7


class TenantThing(IdMixin, TenantMixin, AuditMixin, Base):
    """An ordinary tenant-scoped table."""

    __tablename__ = "tenant_thing"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    qty: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)


class SharedThing(IdMixin, TenantMixin, Base):
    """Stands in for ``role``: rows at SCOPE_ALL belong to every tenant."""

    __tablename__ = "shared_thing"
    __tenant_shared__ = True

    key: Mapped[str] = mapped_column(String(50), nullable=False)


class RootLike(SelfTenantMixin, Base):
    """Stands in for phase 2's ``tenant``: its own ``id`` is the tenant id.

    Here rather than in the ``identity`` suite because the filter that makes it
    work lives in this library, and the mechanism is tested where it is written.
    """

    __tablename__ = "root_like"

    name: Mapped[str] = mapped_column(String(50), nullable=False)


class ExemptThing(IdMixin, Base):
    """Stands in for a reference table: no ``TenantMixin``, so never filtered."""

    __tablename__ = "exempt_thing"

    code: Mapped[str] = mapped_column(String(10), nullable=False)


class PlaceLike(IdMixin, Base):
    """Stands in for phase 3's ``company`` and ``company_address``.

    It exists to prove that ``uq_state_country_code_code`` can actually carry a
    composite foreign key on ``(country_code, state_code)``. Without a table
    declaring one, that unique key looks redundant against the primary key on
    ``code`` and would eventually be "simplified" away — taking with it the only
    thing that makes ``country_code='IN'`` with ``state_code='US-CA'``
    unrepresentable rather than merely unlikely
    (``docs/identity-schema.md`` §1.2).
    """

    __tablename__ = "place_like"
    __table_args__ = (
        ForeignKeyConstraint(
            ["country_code", "state_code"],
            ["state.country_code", "state.code"],
            name="fk_place_like_country_code",
        ),
    )

    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    state_code: Mapped[str] = mapped_column(String(6), nullable=False)


class CompanyThing(IdMixin, TenantMixin, Base):
    """Owned reference used to test the shared same-company access helper."""

    __tablename__ = "company_thing"
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
