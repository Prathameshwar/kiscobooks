"""report_job; one atomic CREATE with tenant/company constraints."""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_job (
	generation_id BINARY(16) NOT NULL,
	parent_id BINARY(16),
	actor_id BINARY(16) NOT NULL,
	kind VARCHAR(10) NOT NULL,
	lane VARCHAR(10) NOT NULL,
	status VARCHAR(12) NOT NULL,
	definition JSON NOT NULL,
	parameters JSON NOT NULL,
	display JSON NOT NULL,
	permission_hash VARCHAR(64) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	attempt INTEGER NOT NULL,
	lease_until DATETIME(6),
	available_at DATETIME(6) NOT NULL,
	completed_rows BIGINT NOT NULL,
	result JSON,
	failure_code VARCHAR(60),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_job PRIMARY KEY (id),
	CONSTRAINT ck_report_job_report_job_status CHECK (status IN ('QUEUED','RUNNING','COMPLETE','FAILED','BLOCKED','CANCELLED')),
	CONSTRAINT ck_report_job_report_job_kind CHECK (kind IN ('RUN','EXPORT') AND lane IN ('SHORT','BULK','RENDER')),
	CONSTRAINT ck_report_job_report_job_bounds CHECK (attempt >= 0 AND completed_rows >= 0 AND row_version > 0),
	CONSTRAINT ck_report_job_report_job_parent CHECK ((kind='RUN' AND parent_id IS NULL) OR (kind='EXPORT' AND parent_id IS NOT NULL)),
	CONSTRAINT uq_report_job_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_job_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id),
	CONSTRAINT fk_report_job_parent_id FOREIGN KEY(tenant_id, company_id, parent_id) REFERENCES report_job (tenant_id, company_id, id),
	INDEX ix_report_job_page (tenant_id, company_id, id),
	INDEX ix_report_job_parent (tenant_id, company_id, parent_id, id),
	INDEX ix_report_job_schedule (tenant_id, status, lane, available_at, id),
	INDEX ix_report_job_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_job")
