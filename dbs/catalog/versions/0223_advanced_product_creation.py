"""Retain exact advanced product submissions and their progress."""

import sqlalchemy as sa
from alembic import op

revision = "0223"
down_revision = "0222"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE advanced_product_creation (
    id BINARY(16) NOT NULL PRIMARY KEY,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    owner_user_id BINARY(16) NOT NULL,
    command_key VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    request JSON NOT NULL,
    status VARCHAR(16) NOT NULL,
    step VARCHAR(32) NOT NULL,
    row_version INTEGER NOT NULL,
    family_id BINARY(16) NOT NULL,
    sku_ids JSON NOT NULL,
    progress JSON NOT NULL,
    lease_token BINARY(16) NULL,
    lease_expires_at DATETIME(6) NULL,
    CONSTRAINT uq_advanced_product_creation_key
        UNIQUE (tenant_id, company_id, owner_user_id, command_key),
    INDEX ix_advanced_product_creation_tenant_id (tenant_id),
    INDEX ix_advanced_product_creation_owner
        (tenant_id, company_id, owner_user_id, id),
    CONSTRAINT ck_advanced_product_creation_advanced_product_creation_version
        CHECK (row_version >= 1),
    CONSTRAINT ck_advanced_product_creation_advanced_product_creation_status
        CHECK (status IN ('DEFINED','SETUP','ACTIVATING','OPENING','COMPLETE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM advanced_product_creation")
    ):
        raise RuntimeError("export advanced product creation receipts before downgrade")
    op.execute("DROP TABLE advanced_product_creation")
