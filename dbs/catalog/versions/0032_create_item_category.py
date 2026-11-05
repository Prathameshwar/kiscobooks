"""Catalog-owned item_category; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_category (
    scheme_id BINARY(16) NOT NULL,
    parent_id BINARY(16) NULL,
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
    CONSTRAINT pk_item_category PRIMARY KEY (id),
    CONSTRAINT uq_item_category_scope_id UNIQUE (tenant_id, company_id, scheme_id, id),
    CONSTRAINT uq_item_category_scope_code UNIQUE (tenant_id, company_id, scheme_id, code),
    CONSTRAINT fk_item_category_scheme FOREIGN KEY(tenant_id, company_id, scheme_id) REFERENCES
        category_scheme (tenant_id, company_id, id),
    CONSTRAINT fk_item_category_parent FOREIGN KEY(tenant_id, company_id, scheme_id, parent_id)
        REFERENCES item_category (tenant_id, company_id, scheme_id, id),
    CONSTRAINT ck_item_category_item_category_self CHECK (parent_id IS NULL OR parent_id <> id),
    CONSTRAINT ck_item_category_item_category_version CHECK (row_version > 0),
    KEY ix_item_category_company_code (tenant_id, company_id, code, id),
    KEY ix_item_category_company_name (tenant_id, company_id, name, id),
    KEY ix_item_category_parent (tenant_id, company_id, scheme_id, parent_id, id),
    KEY ix_item_category_scope_name_id (tenant_id, company_id, scheme_id, name, id),
    KEY ix_item_category_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_category")
