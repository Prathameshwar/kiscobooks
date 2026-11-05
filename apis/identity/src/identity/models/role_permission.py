"""``role_permission`` — which catalogue keys a role grants.

docs/identity-schema.md §5.2. ``permission_key`` is a plain ``VARCHAR`` with **no
foreign key**, because there is no ``permission`` table: permissions are a fixed
catalogue in code (CLAUDE.md invariant 13, ``billing_platform.permissions``). The
compensating control for the missing constraint is the **boot check** — a stored key
absent from the catalogue fails startup, because a role granting a key no code
recognizes grants nothing, silently, forever.

**This table carries ``tenant_id``, which §5.2's mixin list omits.** A child with no
``tenant_id`` sits outside the session-level filter, so every read of it would have to
remember to join through ``role`` and constrain the parent — per-query discipline,
which is precisely what CLAUDE.md §5.3 forbids. One forgotten join here leaks the
shape of another tenant's roles.

The column is not a duplicate to keep in step by hand: the composite foreign key
``(role_id, tenant_id)`` → ``role (id, tenant_id)`` makes a row whose ``tenant_id``
disagrees with its role's unstorable. Without it, a tenant could attach a permission
row to another tenant's role and the filter would happily show it to them.
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class RolePermission(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §5.2."""

    __tablename__ = "role_permission"
    #: Follows ``role``: the twelve system roles live at ``SCOPE_ALL``, so their
    #: permission rows must be visible to every tenant too. Without this the shipped
    #: roles resolve to the empty permission set — every route denying every actor,
    #: which is safe and completely unusable.
    __tenant_shared__ = True

    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_key", name="uq_role_permission_role_id_permission_key"
        ),
        # The tenant-agreement constraint. Composite rather than a plain FK to
        # `role.id`, which would let the two `tenant_id`s differ.
        ForeignKeyConstraint(
            ["role_id", "tenant_id"],
            ["role.id", "role.tenant_id"],
            name="fk_role_permission_role_id_tenant_id",
        ),
        # Leads with `role_id` rather than `tenant_id`, under §1.7's first exception:
        # an index supporting a foreign key must lead with the FK's own columns, in
        # the FK's order, or InnoDB invents one. It also happens to be the shape of
        # the resolution query — this role's keys, then the injected tenant filter.
        Index("ix_role_permission_role_id_tenant_id", "role_id", "tenant_id"),
        MARIADB_TABLE_ARGS,
    )

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: ``[CODE]`` — validated against ``billing_platform.permissions.PERMISSIONS`` on
    #: write (422) and again at boot (fail). 80 characters is well clear of the
    #: longest catalogue key; a shorter column would truncate on write and store a key
    #: that matches nothing.
    permission_key: Mapped[str] = mapped_column(String(80), nullable=False)
