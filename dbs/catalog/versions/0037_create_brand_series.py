"""Create brand_series; one atomic DDL, with a paired model."""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE brand_series (
    brand_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT ck_brand_series_brand_series_version CHECK (row_version >= 1),
    CONSTRAINT fk_brand_series_brand FOREIGN KEY(tenant_id, company_id, brand_id) REFERENCES brand
        (tenant_id, company_id, id),
    CONSTRAINT pk_brand_series PRIMARY KEY (id),
    CONSTRAINT uq_brand_series_parent_id UNIQUE (tenant_id, company_id, brand_id, id),
    CONSTRAINT uq_brand_series_scope_code UNIQUE (tenant_id, company_id, brand_id, code),
    CONSTRAINT uq_brand_series_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_brand_series_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_brand_series_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_brand_series_code (tenant_id, company_id, code, id),
    KEY ix_brand_series_name (tenant_id, company_id, name, id),
    KEY ix_brand_series_parent_name (tenant_id, company_id, brand_id, name, id),
    KEY ix_brand_series_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE brand_series")
