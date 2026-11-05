"""Create bulk_change_set; one reversible DDL."""
from alembic import op

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bulk_change_set (
	job_id BINARY(16) NOT NULL,
	logical_key VARCHAR(64) NOT NULL,
	ordinal INTEGER NOT NULL,
	record_count INTEGER NOT NULL,
	action_hash VARCHAR(64) NOT NULL,
	state VARCHAR(12) NOT NULL,
	error_code VARCHAR(64) NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bulk_change_set PRIMARY KEY (id),
	CONSTRAINT uq_bulk_change_set_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_change_set_version CHECK (row_version >= 1),
	CONSTRAINT fk_bulk_change_set_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES bulk_job (tenant_id, company_id, id),
	CONSTRAINT uq_bulk_change_set_job UNIQUE (tenant_id, company_id, job_id, id),
	CONSTRAINT uq_bulk_change_set_key UNIQUE (tenant_id, company_id, job_id, logical_key),
	CONSTRAINT ck_bulk_change_set_bounds CHECK (ordinal >= 1 AND record_count BETWEEN 1 AND 100),
	CONSTRAINT ck_bulk_change_set_state CHECK (state IN ('STAGED','VALID','INVALID','BLOCKED','APPLIED','FAILED','EXCLUDED')),
    INDEX ix_bulk_change_set_order (tenant_id, company_id, job_id, ordinal, id),
    INDEX ix_bulk_change_set_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bulk_change_set")
