"""Create delivery_attempt; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE delivery_attempt (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    delivery_id BINARY(16) NOT NULL,
    attempt_number SMALLINT UNSIGNED NOT NULL,
    provider_account_id BINARY(16) NOT NULL,
    sender_identity_id BINARY(16) NOT NULL,
    attempt_key VARCHAR(255) NOT NULL,
    provider_message_id VARCHAR(255) NULL,
    started_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    latency_ms INT UNSIGNED NULL,
    outcome VARCHAR(30) NOT NULL,
    http_status SMALLINT UNSIGNED NULL,
    provider_error_code VARCHAR(120) NULL,
    error_class VARCHAR(80) NULL,
    retry_after_at DATETIME(6) NULL,
    request_sha256 BINARY(32) NOT NULL,
    response_sha256 BINARY(32) NULL,
    metadata JSON NULL,
    CONSTRAINT pk_delivery_attempt PRIMARY KEY (id),
    CONSTRAINT uq_delivery_attempt_number UNIQUE (delivery_id, attempt_number),
    CONSTRAINT uq_delivery_attempt_provider_key UNIQUE (provider_account_id, attempt_key),
    CONSTRAINT fk_delivery_attempt_delivery_id FOREIGN KEY (delivery_id) REFERENCES notification_delivery (id),
    CONSTRAINT fk_delivery_attempt_provider_account_id FOREIGN KEY (provider_account_id) REFERENCES provider_account (id),
    CONSTRAINT fk_delivery_attempt_sender_identity_id FOREIGN KEY (sender_identity_id) REFERENCES sender_identity (id),
    KEY ix_delivery_attempt_tenant_id (tenant_id),
    KEY ix_delivery_attempt_provider_message (provider_account_id, provider_message_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE delivery_attempt")

