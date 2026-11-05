"""Create brand; one atomic DDL, with a paired model."""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE brand (
    parent_brand_id BINARY(16) NULL,
    owner_party_id BINARY(16) NULL,
    custom_fields JSON NULL,
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
    CONSTRAINT ck_brand_brand_self CHECK (parent_brand_id IS NULL OR parent_brand_id <> id),
    CONSTRAINT ck_brand_brand_version CHECK (row_version >= 1),
    CONSTRAINT fk_brand_parent FOREIGN KEY(tenant_id, company_id, parent_brand_id) REFERENCES brand
        (tenant_id, company_id, id),
    CONSTRAINT pk_brand PRIMARY KEY (id),
    CONSTRAINT uq_brand_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_brand_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_brand_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_brand_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_brand_name (tenant_id, company_id, name, id),
    KEY ix_brand_parent (tenant_id, company_id, parent_brand_id, id),
    KEY ix_brand_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE brand")
