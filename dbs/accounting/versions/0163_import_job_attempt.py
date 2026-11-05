"""Shared import storage: import_job_attempt; one reversible DDL."""
from alembic import op

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_job_attempt (
	revision_id BINARY(16) NOT NULL, 
	phase VARCHAR(8) NOT NULL, 
	outcome VARCHAR(12) NOT NULL, 
	finished_at DATETIME(6) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_job_attempt PRIMARY KEY (id), 
	CONSTRAINT uq_import_job_attempt_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_job_attempt_revision_id FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES import_job_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_import_job_attempt_import_attempt_phase CHECK (phase IN ('VALIDATE','IMPORT')),
KEY ix_import_job_attempt_page (tenant_id, company_id, id),
KEY ix_import_job_attempt_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_job_attempt")
