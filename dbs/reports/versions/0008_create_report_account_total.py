"""report_account_total; one atomic DDL statement."""
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE report_account_total (\n\tgeneration_id BINARY(16) NOT NULL, \n\taccount_id BINARY(16) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tgrain VARCHAR(10) NOT NULL, \n\tstart_date DATE NOT NULL, \n\tdebit NUMERIC(19, 4) NOT NULL, \n\tcredit NUMERIC(19, 4) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_account_total PRIMARY KEY (id), \n\tCONSTRAINT ck_report_account_total_report_account_total_version CHECK (row_version > 0), \n\tCONSTRAINT uq_report_account_total_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_report_account_total_grain UNIQUE (tenant_id, company_id, generation_id, account_id, currency, grain, start_date), \n\tCONSTRAINT fk_report_account_total_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_account_total_report_account_total_valid CHECK (grain IN ('DAY','MONTH') AND debit >= 0 AND credit >= 0),\n\tINDEX ix_report_account_total_page (tenant_id, company_id, id),\n\tINDEX ix_report_account_total_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_account_total")
