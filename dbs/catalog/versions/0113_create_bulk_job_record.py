"""Create bulk_job_record; one reversible DDL."""
from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bulk_job_record (
	job_id BINARY(16) NOT NULL,
	change_set_id BINARY(16) NOT NULL,
	logical_key VARCHAR(64) NOT NULL,
	ordinal INTEGER NOT NULL,
	resource VARCHAR(80) NOT NULL,
	action VARCHAR(40) NOT NULL,
	target_id BINARY(16) NULL,
	target_key VARCHAR(64) NULL,
	expected_version INTEGER NULL,
	source_sheet VARCHAR(100) NOT NULL,
	source_row INTEGER NOT NULL,
	state VARCHAR(12) NOT NULL,
	normalized_input JSON NOT NULL,
	prepared_input JSON NULL,
	preview JSON NULL,
	source_pins JSON NULL,
	error_code VARCHAR(64) NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bulk_job_record PRIMARY KEY (id),
	CONSTRAINT uq_bulk_job_record_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_job_record_version CHECK (row_version >= 1),
	CONSTRAINT fk_bulk_job_record_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES bulk_job (tenant_id, company_id, id),
	CONSTRAINT uq_bulk_job_record_job UNIQUE (tenant_id, company_id, job_id, id),
	CONSTRAINT fk_bulk_job_record_change_set_id FOREIGN KEY(tenant_id, company_id, job_id, change_set_id) REFERENCES bulk_change_set (tenant_id, company_id, job_id, id),
	CONSTRAINT uq_bulk_job_record_key UNIQUE (tenant_id, company_id, job_id, logical_key),
	CONSTRAINT ck_bulk_job_record_bounds CHECK (ordinal >= 1 AND source_row >= 1),
	CONSTRAINT ck_bulk_job_record_expected_version CHECK (expected_version IS NULL OR expected_version >= 1),
	CONSTRAINT ck_bulk_job_record_state CHECK (state IN ('STAGED','VALID','INVALID','BLOCKED','APPLIED','FAILED','EXCLUDED')),
    INDEX ix_bulk_job_record_order (tenant_id, company_id, job_id, ordinal, id),
    INDEX ix_bulk_job_record_set (tenant_id, company_id, change_set_id, ordinal, id),
    INDEX ix_bulk_job_record_target (tenant_id, company_id, job_id, resource, target_key, id),
    INDEX ix_bulk_job_record_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bulk_job_record")
