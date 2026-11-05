"""Create provider_account; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE provider_account (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    `key` VARCHAR(80) NOT NULL,
    callback_key CHAR(43) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    channel VARCHAR(20) NOT NULL,
    provider_key VARCHAR(60) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    credential_ref VARCHAR(500) NOT NULL,
    callback_secret_ref VARCHAR(500) NULL,
    region VARCHAR(40) NULL,
    status VARCHAR(20) NOT NULL,
    capabilities JSON NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_provider_account PRIMARY KEY (id),
    CONSTRAINT uq_provider_account_tenant_id_key UNIQUE (tenant_id, `key`),
    CONSTRAINT uq_provider_account_callback_key UNIQUE (callback_key),
    KEY ix_provider_account_tenant_id (tenant_id),
    KEY ix_provider_account_tenant_id_channel_status (tenant_id, channel, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE provider_account")

