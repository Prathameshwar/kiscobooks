"""Shared import storage: import_record_result; one reversible DDL."""
from alembic import op

revision = "0165"
down_revision = "0164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_record_result (
	attempt_id BINARY(16) NOT NULL, 
	record_id BINARY(16) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	business_id BINARY(16) NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_record_result PRIMARY KEY (id), 
	CONSTRAINT uq_import_record_result_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_record_result_attempt_id FOREIGN KEY(tenant_id, company_id, attempt_id) REFERENCES import_job_attempt (tenant_id, company_id, id), 
	CONSTRAINT fk_import_record_result_record_id FOREIGN KEY(tenant_id, company_id, record_id) REFERENCES import_job_record (tenant_id, company_id, id), 
	CONSTRAINT uq_import_result_record UNIQUE (tenant_id, company_id, attempt_id, record_id),
KEY ix_import_record_result_page (tenant_id, company_id, id),
KEY ix_import_record_result_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_record_result")
