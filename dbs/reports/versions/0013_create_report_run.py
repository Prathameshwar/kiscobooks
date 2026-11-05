"""report_run; one atomic DDL statement."""
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE report_run (\n\tgeneration_id BINARY(16) NOT NULL, \n\tdefinition_id BINARY(16) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tpermission_hash VARCHAR(64) NOT NULL, \n\tparameters JSON NOT NULL, \n\tevidence JSON, \n\tfailure_code VARCHAR(60), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_run PRIMARY KEY (id), \n\tCONSTRAINT ck_report_run_report_run_valid CHECK (status IN ('PENDING','COMPLETE','BLOCKED')), \n\tCONSTRAINT ck_report_run_report_run_version CHECK (row_version > 0), \n\tCONSTRAINT fk_report_run_definition_id FOREIGN KEY(tenant_id, company_id, definition_id) REFERENCES report_definition (tenant_id, company_id, id), \n\tCONSTRAINT fk_report_run_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id), \n\tCONSTRAINT uq_report_run_scope UNIQUE (tenant_id, company_id, id),\n\tINDEX ix_report_run_page (tenant_id, company_id, id),\n\tINDEX ix_report_run_tenant_id (tenant_id),\n\tINDEX ix_report_run_work (tenant_id, company_id, status, id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_run")
