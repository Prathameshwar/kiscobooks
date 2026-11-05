"""Catalog-owned category_scheme; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE category_scheme (
    membership_mode VARCHAR(10) NOT NULL,
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
    CONSTRAINT pk_category_scheme PRIMARY KEY (id),
    CONSTRAINT uq_category_scheme_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_category_scheme_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT ck_category_scheme_category_scheme_mode CHECK (membership_mode IN ('SINGLE',
        'MULTIPLE')),
    CONSTRAINT ck_category_scheme_category_scheme_version CHECK (row_version > 0),
    KEY ix_category_scheme_scope_name_id (tenant_id, company_id, name, id),
    KEY ix_category_scheme_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE category_scheme")
