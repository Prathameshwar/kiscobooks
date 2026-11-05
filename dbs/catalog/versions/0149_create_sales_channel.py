"""Catalog sales_channel: company-owned sales-channel master; one DDL."""

from alembic import op

revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE sales_channel (
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    row_version INT NOT NULL DEFAULT 1,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_sales_channel PRIMARY KEY (id),
    CONSTRAINT uq_sales_channel_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_sales_channel_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT ck_sales_channel_row_version CHECK (row_version >= 1),
    KEY ix_sales_channel_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE sales_channel")
