"""Shared import storage: import_job_record; one reversible DDL."""
from alembic import op

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_job_record (
	change_set_id BINARY(16) NOT NULL, 
	logical_key VARCHAR(64) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	source_file VARCHAR(120) NOT NULL, 
	source_sheet VARCHAR(100) NOT NULL, 
	source_row INTEGER NOT NULL, 
	resource VARCHAR(80) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_job_record PRIMARY KEY (id), 
	CONSTRAINT uq_import_job_record_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_job_record_change_set_id FOREIGN KEY(tenant_id, company_id, change_set_id) REFERENCES import_change_set (tenant_id, company_id, id), 
	CONSTRAINT uq_import_record_key UNIQUE (tenant_id, company_id, change_set_id, logical_key),
KEY ix_import_job_record_page (tenant_id, company_id, id),
KEY ix_import_job_record_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_job_record")
