"""Single-use invitation state. Its public ID is never a login credential."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, StatusMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import Computed, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UserInvitation(IdMixin, TenantMixin, AuditMixin, StatusMixin, Base):
    __tablename__ = "user_invitation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user.tenant_id", "user.id"],
            name="fk_user_invitation_user_owner",
        ),
        Index("ix_user_invitation_user_owner", "tenant_id", "user_id"),
        UniqueConstraint("pending_user_id", name="uq_user_invitation_pending"),
        MARIADB_TABLE_ARGS,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    pending_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        Computed("CASE WHEN status = 'pending' THEN user_id ELSE NULL END", persisted=True),
        nullable=True,
    )
