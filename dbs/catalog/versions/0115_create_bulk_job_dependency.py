"""Create bulk_job_dependency; one reversible DDL."""
from alembic import op

revision = "0115"
down_revision = "0114"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bulk_job_dependency (
	job_id BINARY(16) NOT NULL,
	parent_record_id BINARY(16) NOT NULL,
	child_record_id BINARY(16) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bulk_job_dependency PRIMARY KEY (id),
	CONSTRAINT uq_bulk_job_dependency_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_job_dependency_version CHECK (row_version >= 1),
	CONSTRAINT fk_bulk_job_dependency_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES bulk_job (tenant_id, company_id, id),
	CONSTRAINT fk_bulk_job_dependency_parent_record_id FOREIGN KEY(tenant_id, company_id, job_id, parent_record_id) REFERENCES bulk_job_record (tenant_id, company_id, job_id, id),
	CONSTRAINT fk_bulk_job_dependency_child_record_id FOREIGN KEY(tenant_id, company_id, job_id, child_record_id) REFERENCES bulk_job_record (tenant_id, company_id, job_id, id),
	CONSTRAINT uq_bulk_job_dependency_edge UNIQUE (tenant_id, company_id, job_id, parent_record_id, child_record_id),
	CONSTRAINT ck_bulk_job_dependency_self_edge CHECK (parent_record_id <> child_record_id),
    INDEX ix_bulk_job_dependency_child (tenant_id, company_id, job_id, child_record_id, id),
    INDEX ix_bulk_job_dependency_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bulk_job_dependency")
