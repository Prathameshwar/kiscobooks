"""Create warranty_policy; one DDL paired with its native model."""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE warranty_policy (
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
    CONSTRAINT ck_warranty_policy_warranty_policy_version CHECK (row_version >= 1),
    CONSTRAINT pk_warranty_policy PRIMARY KEY (id),
    CONSTRAINT uq_warranty_policy_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_warranty_policy_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_warranty_policy_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_warranty_policy_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_warranty_policy_name (tenant_id, company_id, name, id),
    KEY ix_warranty_policy_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE warranty_policy")
