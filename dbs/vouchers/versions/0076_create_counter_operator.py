"""Company-scoped counter operator roster; one DDL statement."""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE counter_operator (
    counter_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    status VARCHAR(20) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_counter_operator PRIMARY KEY (id),
    CONSTRAINT uq_counter_operator_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_counter_operator_user UNIQUE (tenant_id, company_id, counter_id, user_id),
    CONSTRAINT ck_counter_operator_status CHECK (status IN ('ACTIVE','INACTIVE')),
    CONSTRAINT fk_counter_operator_counter FOREIGN KEY (tenant_id, company_id, counter_id)
        REFERENCES checkout_counter (tenant_id, company_id, id),
    KEY ix_counter_operator_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE counter_operator")
