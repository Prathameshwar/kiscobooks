"""Create recipient_endpoint; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE recipient_endpoint (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    subject_type VARCHAR(40) NOT NULL,
    subject_id BINARY(16) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    destination_ciphertext BLOB NULL,
    destination_hmac BINARY(32) NOT NULL,
    destination_masked VARCHAR(320) NOT NULL,
    locale VARCHAR(35) NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    verification_status VARCHAR(20) NOT NULL,
    health_status VARCHAR(20) NOT NULL,
    failure_count INT UNSIGNED NOT NULL,
    last_success_at DATETIME(6) NULL,
    last_failure_at DATETIME(6) NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    is_active TINYINT(1) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    CONSTRAINT pk_recipient_endpoint PRIMARY KEY (id),
    CONSTRAINT uq_recipient_endpoint_subject_channel_destination UNIQUE (tenant_id, subject_type, subject_id, channel, destination_hmac),
    KEY ix_recipient_endpoint_tenant_id (tenant_id),
    KEY ix_recipient_endpoint_tenant_subject (tenant_id, subject_type, subject_id),
    KEY ix_recipient_endpoint_tenant_destination (tenant_id, destination_hmac)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE recipient_endpoint")
