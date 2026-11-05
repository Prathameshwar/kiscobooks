"""Shared import storage: import_job; one reversible DDL."""
from alembic import op

revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_job (
	actor_user_id BINARY(16) NOT NULL, 
	template_id BINARY(16) NOT NULL, 
	definition VARCHAR(40) NOT NULL, 
	state VARCHAR(12) NOT NULL, 
	revision INTEGER NOT NULL, 
	row_version INTEGER NOT NULL, 
	record_count INTEGER NOT NULL, 
	completed_count INTEGER NOT NULL, 
	review_digest VARCHAR(64) NULL, 
	context_digest VARCHAR(64) NULL, 
	expires_at DATETIME(6) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_job PRIMARY KEY (id), 
	CONSTRAINT uq_import_job_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_job_template_id FOREIGN KEY(tenant_id, company_id, template_id) REFERENCES import_template_snapshot (tenant_id, company_id, id), 
	CONSTRAINT ck_import_job_import_job_bounds CHECK (revision >= 1 AND row_version >= 1 AND record_count BETWEEN 1 AND 200), 
	CONSTRAINT ck_import_job_import_job_state CHECK (state IN ('STAGED','READY','INVALID','SUCCEEDED','PARTIAL','FAILED','CANCELLED','EXPIRED')),
KEY ix_import_job_expiry (tenant_id, company_id, expires_at, id),
KEY ix_import_job_actor (tenant_id, company_id, actor_user_id, id),
KEY ix_import_job_page (tenant_id, company_id, id),
KEY ix_import_job_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_job")
