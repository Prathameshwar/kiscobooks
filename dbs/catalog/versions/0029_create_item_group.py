"""Catalog-owned item_group; one CREATE/DROP, no seed data."""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_group (
    allowed_kind VARCHAR(10) NOT NULL,
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
    CONSTRAINT pk_item_group PRIMARY KEY (id),
    CONSTRAINT uq_item_group_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_item_group_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT ck_item_group_item_group_kind CHECK (allowed_kind IN ('GOODS', 'SERVICE', 'BOTH')),
    CONSTRAINT ck_item_group_item_group_version CHECK (row_version > 0),
    KEY ix_item_group_scope_name_id (tenant_id, company_id, name, id),
    KEY ix_item_group_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_group")
