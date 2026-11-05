"""Scoped checkout lane; one DDL statement."""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE checkout_counter (
    outlet_id BINARY(16) NOT NULL,
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
    CONSTRAINT pk_checkout_counter PRIMARY KEY (id),
    CONSTRAINT uq_checkout_counter_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_checkout_counter_code UNIQUE (tenant_id, company_id, outlet_id, code),
    CONSTRAINT fk_checkout_counter_outlet FOREIGN KEY (tenant_id, company_id, outlet_id)
        REFERENCES counter_outlet (tenant_id, company_id, id),
    KEY ix_checkout_counter_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE checkout_counter")
