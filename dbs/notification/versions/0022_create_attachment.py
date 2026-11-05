"""Create attachment; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE attachment (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    storage_key VARCHAR(500) NOT NULL,
    filename_ciphertext BLOB NOT NULL,
    media_type VARCHAR(255) NOT NULL,
    byte_size BIGINT UNSIGNED NOT NULL,
    sha256 BINARY(32) NOT NULL,
    scan_status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    purged_at DATETIME(6) NULL,
    CONSTRAINT pk_attachment PRIMARY KEY (id),
    CONSTRAINT uq_attachment_storage_key UNIQUE (tenant_id, storage_key),
    KEY ix_attachment_tenant_id (tenant_id),
    KEY ix_attachment_expiry (tenant_id, expires_at),
    KEY ix_attachment_scan (tenant_id, scan_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE attachment")

