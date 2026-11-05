"""Durable company setup: company_setup_step; one atomic DDL."""
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_setup_step (
	company_id BINARY(16) NOT NULL,
	`key` VARCHAR(60) NOT NULL,
	status VARCHAR(20) NOT NULL,
	evidence JSON NOT NULL,
	failure_code VARCHAR(60),
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_company_setup_step PRIMARY KEY (id),
	CONSTRAINT uq_company_setup_step UNIQUE (tenant_id, company_id, `key`),
	CONSTRAINT fk_company_setup_step_tenant_id FOREIGN KEY(tenant_id, company_id) REFERENCES company (tenant_id, id),
	KEY ix_company_setup_step_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    # Deployment rollback must retain setup/audit evidence until explicitly archived.
    op.execute("DROP TABLE company_setup_step")
