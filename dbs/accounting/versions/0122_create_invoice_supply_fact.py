"""invoice_supply_fact; one atomic CREATE."""
from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE invoice_supply_fact (\n\tinvoice_id BINARY(16) NOT NULL, \n\tline_key BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\taccount_id BINARY(16) NOT NULL, \n\tsupply_kind VARCHAR(10) NOT NULL, \n\tdescription VARCHAR(1000) NOT NULL, \n\tentered NUMERIC(19, 4) NOT NULL, \n\tcommercial NUMERIC(19, 4) NOT NULL, \n\ttaxable NUMERIC(19, 4) NOT NULL, \n\tprice_rounding NUMERIC(19, 4) NOT NULL, \n\tpayable NUMERIC(19, 4) NOT NULL, \n\ttax_profile VARCHAR(40) NOT NULL, \n\tdate_contract_version INTEGER NOT NULL, \n\ttax_point_date DATE, \n\ttax_point_basis VARCHAR(40), \n\tservice_completion_date DATE, \n\tcompany_registration_id BINARY(16), \n\tparty_registration_id BINARY(16), \n\tplace_of_supply VARCHAR(10), \n\tsupply_context VARCHAR(20), \n\tclassification_code VARCHAR(8), \n\ttreatment VARCHAR(10) NOT NULL, \n\treverse_charge BOOL NOT NULL, \n\tcredit_state VARCHAR(20) NOT NULL, \n\tsupplier_invoice_number VARCHAR(120), \n\tsupplier_invoice_date DATE, \n\tsource_evidence JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_supply_fact PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_supply_fact_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_supply_fact_tenant_id_company_id_invoice_id_line_key UNIQUE (tenant_id, company_id, invoice_id, line_key), \n\tCONSTRAINT ck_invoice_supply_fact_amounts CHECK (entered >= 0 AND commercial >= 0 AND taxable >= 0 AND payable >= 0), \n\tCONSTRAINT ck_invoice_supply_fact_date_version CHECK (date_contract_version = 2), \n\tCONSTRAINT uq_invoice_supply_fact_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_supply_fact_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_supply_fact_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_supply_fact_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_supply_fact")
