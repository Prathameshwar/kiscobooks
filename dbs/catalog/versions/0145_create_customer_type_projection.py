"""Catalog customer_type_projection: minimal Billing-sourced customer-type identity; one DDL."""

from alembic import op

revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE customer_type_projection (
    code VARCHAR(40) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    parent_code VARCHAR(40) NULL,
    is_active TINYINT(1) NOT NULL,
    company_id BINARY(16) NOT NULL,
    source_id BINARY(16) NOT NULL,
    source_version BIGINT NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    CONSTRAINT pk_customer_type_projection PRIMARY KEY (id),
    CONSTRAINT uq_customer_type_projection_source UNIQUE (tenant_id, company_id, source_id),
    CONSTRAINT ck_customer_type_projection_source_version CHECK (source_version > 0),
    KEY ix_customer_type_projection_tenant_id (tenant_id),
    KEY ix_customer_type_projection_lookup_0 (tenant_id, company_id, code)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE customer_type_projection")
