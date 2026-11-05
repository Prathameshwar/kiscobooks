"""``user_group`` — a named set of users, a subject for role assignment.

docs/identity-schema.md §4.5, docs/org-model.md §2.5. Assigning a role to a group grants
it to every member; membership of the group is ``user_group_member``. Deliberately
**flat** — no ``parent_id`` (org-model §5 recommends against group nesting, which turns a
simple set into a second, silent, permission hierarchy).
"""

from __future__ import annotations

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UserGroup(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §4.5."""

    __tablename__ = "user_group"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_user_group_tenant_id_code"),
        MARIADB_TABLE_ARGS,
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
