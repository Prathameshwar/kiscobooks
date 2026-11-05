"""report_job_attempt; one atomic CREATE with tenant/company constraints."""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_job_attempt (
	job_id BINARY(16) NOT NULL,
	attempt INTEGER NOT NULL,
	started_at DATETIME(6) NOT NULL,
	finished_at DATETIME(6),
	outcome VARCHAR(20),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_job_attempt PRIMARY KEY (id),
	CONSTRAINT uq_report_job_attempt_number UNIQUE (tenant_id, company_id, job_id, attempt),
	CONSTRAINT ck_report_job_attempt_report_job_attempt_positive CHECK (attempt > 0),
	CONSTRAINT uq_report_job_attempt_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_job_attempt_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES report_job (tenant_id, company_id, id),
	INDEX ix_report_job_attempt_page (tenant_id, company_id, id),
	INDEX ix_report_job_attempt_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_job_attempt")
