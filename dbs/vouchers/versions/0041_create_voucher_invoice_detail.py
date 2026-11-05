"""voucher_invoice_detail; one atomic CREATE with revision-scoped ownership."""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_invoice_detail (\n\trevision_id BINARY(16) NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\tparty_line_key BINARY(16) NOT NULL, \n\tparty_account_id BINARY(16) NOT NULL, \n\tparty_account_version INTEGER NOT NULL, \n\tbill_reference VARCHAR(120) NOT NULL, \n\tdue_date DATE NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\texchange_rate NUMERIC(19, 8) NOT NULL, \n\trounding_increment NUMERIC(19, 4), \n\trounding_account_id BINARY(16), \n\trounding_account_version INTEGER, \n\tsupplier_declared_total NUMERIC(19, 4), \n\tsupplier_difference_reason VARCHAR(500), \n\tdate_contract_version INTEGER NOT NULL, \n\tprofile VARCHAR(40) NOT NULL, \n\tcompany_registration_id BINARY(16), \n\tparty_registration_id BINARY(16), \n\tplace_of_supply VARCHAR(10), \n\tservice_completion_date DATE, \n\tpayment_date DATE, \n\tsupplier_invoice_number VARCHAR(120), \n\tsupplier_invoice_date DATE, \n\twithholding_section_id BINARY(16), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_invoice_detail PRIMARY KEY (id), \n\tCONSTRAINT ck_voucher_invoice_detail_voucher_invoice_declared CHECK (supplier_declared_total IS NULL OR supplier_declared_total >= 0), \n\tCONSTRAINT ck_voucher_invoice_detail_voucher_invoice_versions CHECK (schema_version = 1 AND date_contract_version = 2), \n\tCONSTRAINT uq_voucher_invoice_detail_tenant_id_company_id_revision_id UNIQUE (tenant_id, company_id, revision_id), \n\tCONSTRAINT uq_voucher_invoice_detail_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_invoice_detail_tenant_id_company_id_revision_id_id UNIQUE (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT ck_voucher_invoice_detail_voucher_invoice_values CHECK (exchange_rate > 0 AND party_account_version > 0), \n\tCONSTRAINT fk_voucher_invoice_detail_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT ck_voucher_invoice_detail_voucher_invoice_rounding CHECK (rounding_increment IS NULL OR rounding_increment > 0), \n\tCONSTRAINT ck_voucher_invoice_detail_voucher_invoice_round_account CHECK ((rounding_account_id IS NULL AND rounding_account_version IS NULL) OR (rounding_account_id IS NOT NULL AND rounding_account_version IS NOT NULL AND rounding_account_version > 0)),\n\tINDEX ix_voucher_invoice_detail_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_invoice_detail")
