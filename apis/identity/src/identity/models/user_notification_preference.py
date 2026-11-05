"""``user_notification_preference`` — a user's per-event, per-channel opt-in.

docs/identity-schema.md §4.3. ``identity`` is master; the ``notification`` service holds a
read-only projection of this (docs/notification.md). An absent row means the event's
default applies — the table records only deviations.
"""

from __future__ import annotations

import uuid
from typing import Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

NOTIFICATION_CHANNELS: Final[frozenset[str]] = frozenset(
    {"email", "sms", "whatsapp", "push", "in_app"}
)


class UserNotificationPreference(IdMixin, TenantMixin, Base):
    """docs/identity-schema.md §4.3. No audit/lifecycle columns — a preference is a
    current value, not a document with a history."""

    __tablename__ = "user_notification_preference"
    __table_args__ = (
        # Leads with `user_id`, so it also supports that FK.
        UniqueConstraint(
            "user_id", "channel", "event_key", name="uq_user_notif_pref_user_channel_event"
        ),
        MARIADB_TABLE_ARGS,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("user.id", name="fk_user_notification_preference_user_id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    #: `[CODE]` from the notifiable-event catalogue; no FK (it is code, not data).
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
