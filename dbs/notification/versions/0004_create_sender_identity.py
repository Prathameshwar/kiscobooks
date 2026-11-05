"""Create sender_identity; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE sender_identity (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    provider_account_id BINARY(16) NOT NULL,
    `key` VARCHAR(80) NOT NULL,
    sender_type VARCHAR(30) NOT NULL,
    external_sender_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    reply_to_ciphertext BLOB NULL,
    verification_status VARCHAR(20) NOT NULL,
    capabilities JSON NULL,
    verified_at DATETIME(6) NULL,
    is_active TINYINT(1) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT pk_sender_identity PRIMARY KEY (id),
    CONSTRAINT uq_sender_identity_provider_key UNIQUE (provider_account_id, `key`),
    CONSTRAINT uq_sender_identity_provider_external UNIQUE (provider_account_id, external_sender_id),
    CONSTRAINT fk_sender_identity_provider_account_id FOREIGN KEY (provider_account_id) REFERENCES provider_account (id),
    KEY ix_sender_identity_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE sender_identity")

