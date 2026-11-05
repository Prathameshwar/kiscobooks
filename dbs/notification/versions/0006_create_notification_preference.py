"""Create notification_preference; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE notification_preference (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    subject_type VARCHAR(40) NOT NULL,
    subject_id BINARY(16) NOT NULL,
    event_key VARCHAR(120) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    is_enabled TINYINT(1) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    source_updated_at DATETIME(6) NOT NULL,
    projected_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_notification_preference PRIMARY KEY (id),
    CONSTRAINT uq_notification_preference_subject_event_channel UNIQUE (tenant_id, subject_type, subject_id, event_key, channel),
    KEY ix_notification_preference_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE notification_preference")

