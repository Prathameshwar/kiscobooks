"""Shared import storage: import_record_issue; one reversible DDL."""
from alembic import op

revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_record_issue (
	result_id BINARY(16) NOT NULL, 
	field VARCHAR(128) NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	message VARCHAR(250) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_record_issue PRIMARY KEY (id), 
	CONSTRAINT uq_import_record_issue_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_record_issue_result_id FOREIGN KEY(tenant_id, company_id, result_id) REFERENCES import_record_result (tenant_id, company_id, id),
KEY ix_import_record_issue_page (tenant_id, company_id, id),
KEY ix_import_record_issue_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_record_issue")
