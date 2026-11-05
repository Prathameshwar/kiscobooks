"""Shared import storage: import_job_dependency; one reversible DDL."""
from alembic import op

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_job_dependency (
	parent_id BINARY(16) NOT NULL, 
	child_id BINARY(16) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_job_dependency PRIMARY KEY (id), 
	CONSTRAINT uq_import_job_dependency_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_job_dependency_parent_id FOREIGN KEY(tenant_id, company_id, parent_id) REFERENCES import_job_record (tenant_id, company_id, id), 
	CONSTRAINT fk_import_job_dependency_child_id FOREIGN KEY(tenant_id, company_id, child_id) REFERENCES import_job_record (tenant_id, company_id, id), 
	CONSTRAINT ck_import_job_dependency_import_dependency_self CHECK (parent_id <> child_id), 
	CONSTRAINT uq_import_dependency_edge UNIQUE (tenant_id, company_id, parent_id, child_id),
KEY ix_import_job_dependency_page (tenant_id, company_id, id),
KEY ix_import_job_dependency_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_job_dependency")
