"""Shared import storage: import_job_revision; one reversible DDL."""
from alembic import op

revision = "0183"
down_revision = "0182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_job_revision (
	job_id BINARY(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	input_hash VARCHAR(64) NOT NULL, 
	batch JSON NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_job_revision PRIMARY KEY (id), 
	CONSTRAINT uq_import_job_revision_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_job_revision_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES import_job (tenant_id, company_id, id), 
	CONSTRAINT uq_import_revision_number UNIQUE (tenant_id, company_id, job_id, revision),
KEY ix_import_job_revision_page (tenant_id, company_id, id),
KEY ix_import_job_revision_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_job_revision")
