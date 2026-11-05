"""report_result_batch; one atomic CREATE with tenant/company constraints."""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_result_batch (
	job_id BINARY(16) NOT NULL,
	attempt INTEGER NOT NULL,
	first_ordinal BIGINT NOT NULL,
	row_count INTEGER NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	`rows` JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_result_batch PRIMARY KEY (id),
	CONSTRAINT fk_report_result_batch_attempt FOREIGN KEY(tenant_id, company_id, job_id, attempt) REFERENCES report_job_attempt (tenant_id, company_id, job_id, attempt),
	CONSTRAINT uq_report_result_batch_ordinal UNIQUE (tenant_id, company_id, job_id, attempt, first_ordinal),
	CONSTRAINT ck_report_result_batch_report_result_batch_bounds CHECK (attempt > 0 AND first_ordinal > 0 AND row_count BETWEEN 1 AND 200),
	CONSTRAINT uq_report_result_batch_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_result_batch_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES report_job (tenant_id, company_id, id),
	INDEX ix_report_result_batch_page (tenant_id, company_id, id),
	INDEX ix_report_result_batch_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_result_batch")
