"""voucher_bill_instruction; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_bill_instruction (\n\trevision_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tallocation_key BINARY(16) NOT NULL, \n\tdebt_item_id BINARY(16), \n\tdebt_line_key BINARY(16), \n\tcredit_item_id BINARY(16), \n\tcredit_line_key BINARY(16), \n\tamount NUMERIC(19, 4) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tfx_account_id BINARY(16), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_bill_instruction PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_bill_instruction_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_bill_instruction_tenant_id_company_id_revisio_9001 UNIQUE (tenant_id, company_id, revision_id, allocation_key), \n\tCONSTRAINT fk_voucher_bill_instruction_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT ck_voucher_bill_instruction_voucher_bill_instruction_c0 CHECK (amount > 0), \n\tCONSTRAINT ck_voucher_bill_instruction_voucher_bill_instruction_c1 CHECK ((debt_item_id IS NULL) <> (debt_line_key IS NULL)), \n\tCONSTRAINT ck_voucher_bill_instruction_voucher_bill_instruction_c2 CHECK ((credit_item_id IS NULL) <> (credit_line_key IS NULL)),\n\tINDEX ix_voucher_bill_instruction_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_bill_instruction")
