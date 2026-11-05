"""report_artifact; one atomic DDL statement."""
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_artifact (\n\trun_id BINARY(16) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tbody MEDIUMTEXT NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_artifact PRIMARY KEY (id), \n\tCONSTRAINT fk_report_artifact_run_id FOREIGN KEY(tenant_id, company_id, run_id) REFERENCES report_run (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_artifact_report_artifact_version CHECK (row_version > 0), \n\tCONSTRAINT uq_report_artifact_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_report_artifact_run UNIQUE (tenant_id, company_id, run_id),\n\tINDEX ix_report_artifact_page (tenant_id, company_id, id),\n\tINDEX ix_report_artifact_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_artifact")
