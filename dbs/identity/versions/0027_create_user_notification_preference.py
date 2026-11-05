"""create user_notification_preference

Revision ID: 0027
Revises: 0026

A user's per-event, per-channel opt-in (docs/identity-schema.md §4.3). ``identity`` is
master; ``notification`` holds a read-only projection. No audit/lifecycle columns — it is
a current value, not a document with a history. The unique key leads with `user_id` and
supports the FK. ``user`` is backticked — reserved word. Name hand-shortened to fit the
64-char limit (§1.3).

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key · no ENUM · no FLOAT · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE user_notification_preference (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    event_key VARCHAR(120) NOT NULL,
    is_enabled TINYINT(1) NOT NULL,
    CONSTRAINT pk_user_notification_preference PRIMARY KEY (id),
    CONSTRAINT uq_user_notif_pref_user_channel_event UNIQUE (user_id, channel, event_key),
    CONSTRAINT fk_user_notification_preference_user_id FOREIGN KEY (user_id) REFERENCES `user` (id),
    KEY ix_user_notification_preference_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE user_notification_preference")
