"""Attempt-owned export evidence; one atomic CREATE with scoped references."""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_export_artifact (
	job_id BINARY(16) NOT NULL,
	run_id BINARY(16) NOT NULL,
	attempt INTEGER NOT NULL,
	state VARCHAR(12) NOT NULL,
	storage_key VARCHAR(32) NOT NULL,
	media_type VARCHAR(100) NOT NULL,
	filename VARCHAR(100) NOT NULL,
	renderer JSON NOT NULL,
	content_hash VARCHAR(64),
	byte_count BIGINT,
	row_count BIGINT,
	temporary_cleaned_at DATETIME(6),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_export_artifact PRIMARY KEY (id),
	CONSTRAINT fk_report_export_artifact_attempt FOREIGN KEY(tenant_id, company_id, job_id, attempt) REFERENCES report_job_attempt (tenant_id, company_id, job_id, attempt),
	CONSTRAINT uq_report_export_artifact_storage UNIQUE (storage_key),
	CONSTRAINT uq_report_export_artifact_attempt UNIQUE (tenant_id, company_id, job_id, attempt),
	CONSTRAINT ck_report_export_artifact_export_artifact_state CHECK (attempt > 0 AND state IN ('STAGING','PUBLISHED')),
	CONSTRAINT ck_report_export_artifact_export_artifact_evidence CHECK ((state='STAGING' AND content_hash IS NULL AND byte_count IS NULL AND row_count IS NULL) OR (state='PUBLISHED' AND content_hash IS NOT NULL AND byte_count IS NOT NULL AND row_count IS NOT NULL AND byte_count >= 0 AND row_count >= 0)),
	CONSTRAINT uq_report_export_artifact_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_export_artifact_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES report_job (tenant_id, company_id, id),
	CONSTRAINT fk_report_export_artifact_run_id FOREIGN KEY(tenant_id, company_id, run_id) REFERENCES report_job (tenant_id, company_id, id),
	INDEX ix_report_export_artifact_cleanup (tenant_id, company_id, temporary_cleaned_at, id),
	INDEX ix_report_export_artifact_page (tenant_id, company_id, id),
	INDEX ix_report_export_artifact_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_export_artifact")
