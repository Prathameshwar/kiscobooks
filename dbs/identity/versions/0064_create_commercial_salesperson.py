"""Company-scoped commercial representative master."""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE commercial_salesperson (
    company_id BINARY(16) NOT NULL,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(160) NOT NULL,
    user_id BINARY(16) NULL,
    is_active BOOLEAN NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_commercial_salesperson PRIMARY KEY (id),
    CONSTRAINT uq_commercial_salesperson_tenant_id_company_id_id
        UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_commercial_salesperson_tenant_id_company_id_code
        UNIQUE (tenant_id, company_id, code),
    CONSTRAINT fk_commercial_salesperson_company FOREIGN KEY (tenant_id, company_id)
        REFERENCES company (tenant_id, id),
    CONSTRAINT fk_commercial_salesperson_user FOREIGN KEY (tenant_id, user_id)
        REFERENCES user (tenant_id, id),
    KEY ix_commercial_salesperson_tenant_user (tenant_id, user_id),
    KEY ix_commercial_salesperson_tenant_id (tenant_id)
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE commercial_salesperson")
