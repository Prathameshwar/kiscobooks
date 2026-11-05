"""Catalog identifier_namespace: identifier namespace codes; one DDL."""

from alembic import op

revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE identifier_namespace (
    code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    row_version INT NOT NULL DEFAULT 1,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_identifier_namespace PRIMARY KEY (id),
    CONSTRAINT uq_identifier_namespace_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_identifier_namespace_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT ck_identifier_namespace_row_version CHECK (row_version >= 1),
    KEY ix_identifier_namespace_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE identifier_namespace")
