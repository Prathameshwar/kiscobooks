"""Shared import storage: import_change_set; one reversible DDL."""
from alembic import op

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_change_set (
	revision_id BINARY(16) NOT NULL, 
	logical_key VARCHAR(64) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_change_set PRIMARY KEY (id), 
	CONSTRAINT uq_import_change_set_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_change_set_revision_id FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES import_job_revision (tenant_id, company_id, id), 
	CONSTRAINT uq_import_set_key UNIQUE (tenant_id, company_id, revision_id, logical_key),
KEY ix_import_change_set_page (tenant_id, company_id, id),
KEY ix_import_change_set_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_change_set")
