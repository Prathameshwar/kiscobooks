"""Durable company setup: company_setup_run; one atomic DDL."""
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_setup_run (
	company_id BINARY(16) NOT NULL,
	command_key VARCHAR(64) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	plan_version INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	opening_choice VARCHAR(20) NOT NULL,
	opening_reason VARCHAR(500),
	requested_features JSON NOT NULL,
	configuration JSON NOT NULL,
	available_at DATETIME(6) NOT NULL,
	lease_expires_at DATETIME(6),
	lease_token BINARY(16),
	attempt INTEGER NOT NULL,
	failure_code VARCHAR(60),
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_company_setup_run PRIMARY KEY (id),
	CONSTRAINT uq_company_setup_company UNIQUE (tenant_id, company_id),
	CONSTRAINT uq_company_setup_command UNIQUE (tenant_id, command_key),
	CONSTRAINT fk_company_setup_run_tenant_id FOREIGN KEY(tenant_id, company_id) REFERENCES company (tenant_id, id),
	KEY ix_company_setup_pending (status, available_at, id),
	KEY ix_company_setup_run_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    # Deployment rollback must retain setup/audit evidence until explicitly archived.
    op.execute("DROP TABLE company_setup_run")
