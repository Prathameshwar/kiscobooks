"""Retain the complete simple-product command and native owner receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0218"
down_revision = "0217"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE simple_product_creation (
    id BINARY(16) NOT NULL PRIMARY KEY,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    command_key VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    step VARCHAR(32) NOT NULL,
    row_version INTEGER NOT NULL,
    code VARCHAR(30) NOT NULL,
    item_id BINARY(16) NULL,
    request JSON NOT NULL,
    progress JSON NOT NULL,
    lease_token BINARY(16) NULL,
    lease_expires_at DATETIME(6) NULL,
    CONSTRAINT uq_simple_creation_key UNIQUE (tenant_id, company_id, command_key),
    CONSTRAINT uq_simple_creation_code UNIQUE (tenant_id, company_id, code),
    INDEX ix_simple_product_creation_tenant_id (tenant_id),
    INDEX ix_simple_creation_item (tenant_id, company_id, item_id, status),
    CONSTRAINT ck_simple_product_creation_simple_creation_status
        CHECK (status IN ('RUNNING','COMPLETE')),
    CONSTRAINT ck_simple_product_creation_simple_creation_version CHECK (row_version >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    # This table retains cross-service operation receipts and may be the only
    # recovery link to posted stock. Never discard it through an automatic downgrade.
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM simple_product_creation")
    ):
        raise RuntimeError("retain simple product creation receipts and their native owner history")
    op.execute("DROP TABLE simple_product_creation")
