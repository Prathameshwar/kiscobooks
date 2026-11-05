"""Create provider_event; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE provider_event (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    provider_account_id BINARY(16) NOT NULL,
    external_event_key VARCHAR(255) NOT NULL,
    provider_message_id VARCHAR(255) NULL,
    event_type VARCHAR(80) NOT NULL,
    signature_verified TINYINT(1) NOT NULL,
    provider_occurred_at DATETIME(6) NULL,
    received_at DATETIME(6) NOT NULL,
    payload_ciphertext MEDIUMBLOB NULL,
    payload_sha256 BINARY(32) NOT NULL,
    encryption_key_ref VARCHAR(500) NOT NULL,
    delivery_id BINARY(16) NULL,
    processing_status VARCHAR(20) NOT NULL,
    processed_at DATETIME(6) NULL,
    processing_error VARCHAR(500) NULL,
    CONSTRAINT pk_provider_event PRIMARY KEY (id),
    CONSTRAINT uq_provider_event_external UNIQUE (provider_account_id, external_event_key),
    CONSTRAINT fk_provider_event_provider_account_id FOREIGN KEY (provider_account_id) REFERENCES provider_account (id),
    CONSTRAINT fk_provider_event_delivery_id FOREIGN KEY (delivery_id) REFERENCES notification_delivery (id),
    KEY ix_provider_event_tenant_id (tenant_id),
    KEY ix_provider_event_message (provider_account_id, provider_message_id),
    KEY ix_provider_event_processing (tenant_id, processing_status, received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE provider_event")

