"""invoice_record; one atomic CREATE."""
from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE invoice_record (\n\tintent_id BINARY(16) NOT NULL, \n\trevision_id BINARY(16) NOT NULL, \n\tcalculation_version INTEGER NOT NULL, \n\tcalculation_hash VARCHAR(64) NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\tcompany_configuration_hash VARCHAR(64) NOT NULL, \n\tkind VARCHAR(20) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tdocument_date DATE NOT NULL, \n\tposting_date DATE NOT NULL, \n\tparty_account_id BINARY(16) NOT NULL, \n\tbill_reference VARCHAR(120) NOT NULL, \n\tdue_date DATE NOT NULL, \n\tcommercial_total NUMERIC(19, 4) NOT NULL, \n\ttax_total NUMERIC(19, 4) NOT NULL, \n\tcharged_tax_total NUMERIC(19, 4) NOT NULL, \n\trounding NUMERIC(19, 4) NOT NULL, \n\tpayable NUMERIC(19, 4) NOT NULL, \n\tsupplier_declared_total NUMERIC(19, 4), \n\tsupplier_difference NUMERIC(19, 4), \n\tsupplier_difference_reason VARCHAR(500), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_record PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_record_intent_id FOREIGN KEY(tenant_id, company_id, intent_id) REFERENCES voucher_money_intent (tenant_id, company_id, id), \n\tCONSTRAINT fk_invoice_record_party_account_id FOREIGN KEY(tenant_id, company_id, party_account_id) REFERENCES account (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_record_tenant_id_company_id_intent_id UNIQUE (tenant_id, company_id, intent_id), \n\tCONSTRAINT ck_invoice_record_calculation_version CHECK (calculation_version = 1), \n\tCONSTRAINT ck_invoice_record_kind CHECK (kind IN ('SALES','PURCHASE','CREDIT_NOTE','DEBIT_NOTE')), \n\tCONSTRAINT ck_invoice_record_amounts CHECK (commercial_total >= 0 AND tax_total >= 0 AND charged_tax_total >= 0 AND payable > 0), \n\tCONSTRAINT ck_invoice_record_hashes CHECK (LENGTH(calculation_hash) = 64 AND LENGTH(configuration_hash) = 64 AND LENGTH(company_configuration_hash) = 64), \n\tCONSTRAINT uq_invoice_record_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_record_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_record")
