"""Operating outlet; one DDL statement."""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE counter_outlet (
    code VARCHAR(40) NOT NULL,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_counter_outlet PRIMARY KEY (id),
    CONSTRAINT uq_counter_outlet_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_counter_outlet_code UNIQUE (tenant_id, company_id, code),
    KEY ix_counter_outlet_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE counter_outlet")
