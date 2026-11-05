"""Create account_posting_mapping; exactly one DDL statement in each direction."""
from alembic import op

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account_posting_mapping (\n\tpurpose VARCHAR(40) NOT NULL, \n\taccount_id BINARY(16) NOT NULL, \n\tcompany_registration_id BINARY(16), \n\tcurrency VARCHAR(3) NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_posting_mapping PRIMARY KEY (id), \n\tCONSTRAINT ck_account_posting_mapping_account_posting_mapping_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT ck_account_posting_mapping_account_posting_mapping_purpose CHECK (purpose IN ('SALES_REVENUE', 'SERVICE_REVENUE', 'SALES_RETURN', 'PURCHASE_EXPENSE', 'OUTPUT_CGST', 'OUTPUT_SGST', 'OUTPUT_UTGST', 'OUTPUT_IGST', 'INPUT_CGST', 'INPUT_SGST', 'INPUT_UTGST', 'INPUT_IGST', 'CASH_RECEIPT', 'BANK_RECEIPT', 'INVENTORY_VALUE', 'COST_OF_GOODS', 'ROUNDING_GAIN', 'ROUNDING_LOSS')), \n\tCONSTRAINT uq_account_posting_mapping_0 UNIQUE (tenant_id, company_id, purpose, company_registration_id, currency, valid_from), \n\tCONSTRAINT uq_account_posting_mapping_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_posting_mapping_account_posting_mapping_version CHECK (row_version > 0), \n\tCONSTRAINT fk_account_posting_mapping_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),\n\tKEY ix_account_posting_mapping_page (tenant_id, company_id, id),\n\tKEY ix_account_posting_mapping_ref0 (tenant_id, company_id, account_id),\n\tKEY ix_account_posting_mapping_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_posting_mapping")
