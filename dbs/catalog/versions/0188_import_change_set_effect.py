"""Shared import storage: import_change_set_effect; one reversible DDL."""
from alembic import op

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_change_set_effect (
	job_id BINARY(16) NOT NULL, 
	logical_key VARCHAR(64) NOT NULL, 
	action_hash VARCHAR(64) NOT NULL, 
	results JSON NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_change_set_effect PRIMARY KEY (id), 
	CONSTRAINT uq_import_change_set_effect_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_change_set_effect_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES import_job (tenant_id, company_id, id), 
	CONSTRAINT uq_import_effect_key UNIQUE (tenant_id, company_id, job_id, logical_key),
KEY ix_import_change_set_effect_page (tenant_id, company_id, id),
KEY ix_import_change_set_effect_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_change_set_effect")
