"""Create return_policy; one DDL paired with its native model."""

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE return_policy (
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
    CONSTRAINT ck_return_policy_return_policy_version CHECK (row_version >= 1),
    CONSTRAINT pk_return_policy PRIMARY KEY (id),
    CONSTRAINT uq_return_policy_scope_code UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_return_policy_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_return_policy_active_code (tenant_id, company_id, is_active, code, id),
    KEY ix_return_policy_active_name (tenant_id, company_id, is_active, name, id),
    KEY ix_return_policy_name (tenant_id, company_id, name, id),
    KEY ix_return_policy_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE return_policy")
