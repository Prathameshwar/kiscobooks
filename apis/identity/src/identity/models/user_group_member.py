"""``user_group_member`` — a user's membership of a group.

docs/identity-schema.md §4.6. Permission resolution walks *from a user to its groups*,
so the ``(user_id)`` index is the hot path; the unique key stops a user being added to
the same group twice.
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UserGroupMember(IdMixin, TenantMixin, AuditMixin, Base):
    """docs/identity-schema.md §4.6."""

    __tablename__ = "user_group_member"
    __table_args__ = (
        # The unique key leads with `user_group_id`, so it also supports that FK.
        UniqueConstraint(
            "user_group_id", "user_id", name="uq_user_group_member_user_group_id_user_id"
        ),
        # Leads with the FK column (§1.7 first exception) and is the resolution query's
        # direction: given a user, which groups.
        Index("ix_user_group_member_user_id", "user_id"),
        MARIADB_TABLE_ARGS,
    )

    user_group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey("user_group.id", name="fk_user_group_member_user_group_id"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("user.id", name="fk_user_group_member_user_id"), nullable=False
    )
    #: Escalation-guard evidence; no FK (a ``_by`` column, §1.5).
    added_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
