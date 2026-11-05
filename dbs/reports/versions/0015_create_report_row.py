"""report_row; one atomic DDL statement."""
from alembic import op

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_row (\n\trun_id BINARY(16) NOT NULL, \n\tordinal BIGINT NOT NULL, \n\tdata JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_row PRIMARY KEY (id), \n\tCONSTRAINT uq_report_row_ordinal UNIQUE (tenant_id, company_id, run_id, ordinal), \n\tCONSTRAINT uq_report_row_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_report_row_run_id FOREIGN KEY(tenant_id, company_id, run_id) REFERENCES report_run (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_row_report_row_version CHECK (row_version > 0),\n\tINDEX ix_report_row_page (tenant_id, company_id, id),\n\tINDEX ix_report_row_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_row")
