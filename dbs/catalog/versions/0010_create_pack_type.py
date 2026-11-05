"""Catalog pack_type: frozen single-DDL migration paired with its model."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE pack_type (
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
    CONSTRAINT pk_pack_type PRIMARY KEY (id),
    CONSTRAINT ck_pack_type_pack_type_row_version CHECK (row_version > 0),
    CONSTRAINT uq_pack_type_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_pack_type_scope_code UNIQUE (tenant_id, company_id, code),
    KEY ix_pack_type_scope_name_id (tenant_id, company_id, name, id),
    KEY ix_pack_type_tenant_id (tenant_id)
) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE pack_type")
