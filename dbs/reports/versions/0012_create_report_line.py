"""report_line; one atomic DDL statement."""
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE report_line (\n\tgeneration_id BINARY(16) NOT NULL, \n\tsource_id BINARY(16) NOT NULL, \n\tjournal_id BINARY(16) NOT NULL, \n\taccount_id BINARY(16) NOT NULL, \n\tparty_id BINARY(16), \n\t`role` VARCHAR(20), \n\tperiod_id BINARY(16) NOT NULL, \n\tposting_date DATE NOT NULL, \n\tcomponent VARCHAR(20) NOT NULL, \n\tside VARCHAR(10) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\tbase_currency VARCHAR(3) NOT NULL, \n\tbase_amount NUMERIC(19, 4) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_line PRIMARY KEY (id), \n\tCONSTRAINT uq_report_line_source UNIQUE (tenant_id, company_id, generation_id, source_id), \n\tCONSTRAINT uq_report_line_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_report_line_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_line_report_line_version CHECK (row_version > 0), \n\tCONSTRAINT ck_report_line_report_line_valid CHECK (side IN ('DEBIT','CREDIT') AND base_amount > 0 AND ((component = 'PRINCIPAL' AND amount > 0) OR (component = 'FX' AND amount = 0 AND party_id IS NOT NULL))),\n\tINDEX ix_report_line_account_date (tenant_id, company_id, generation_id, account_id, posting_date, id),\n\tINDEX ix_report_line_page (tenant_id, company_id, id),\n\tINDEX ix_report_line_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_line")
