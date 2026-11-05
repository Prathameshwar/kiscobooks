"""Create notification_request; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE notification_request (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    source_service VARCHAR(40) NOT NULL,
    source_message_id BINARY(16) NOT NULL,
    source_event_key VARCHAR(120) NOT NULL,
    event_key VARCHAR(120) NOT NULL,
    category VARCHAR(30) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BINARY(16) NOT NULL,
    correlation_id BINARY(16) NULL,
    causation_id BINARY(16) NULL,
    trace_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    priority TINYINT UNSIGNED NOT NULL,
    scheduled_at DATETIME(6) NULL,
    expires_at DATETIME(6) NULL,
    context_ciphertext MEDIUMBLOB NOT NULL,
    context_sha256 BINARY(32) NOT NULL,
    encryption_key_ref VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    CONSTRAINT pk_notification_request PRIMARY KEY (id),
    CONSTRAINT uq_notification_request_source_message UNIQUE (source_message_id),
    KEY ix_notification_request_tenant_id (tenant_id),
    KEY ix_notification_request_status_schedule (tenant_id, status, scheduled_at),
    KEY ix_notification_request_aggregate (tenant_id, aggregate_type, aggregate_id),
    KEY ix_notification_request_correlation (tenant_id, correlation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE notification_request")

