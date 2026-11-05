"""voucher_tender; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_tender (\n\trevision_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\ttender_key BINARY(16) NOT NULL, \n\tline_key BINARY(16) NOT NULL, \n\tmode VARCHAR(20) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\treference VARCHAR(120), \n\tinstrument_date DATE, \n\trecognition VARCHAR(20) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_tender PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_tender_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_tender_tenant_id_company_id_revision_id_tender_key UNIQUE (tenant_id, company_id, revision_id, tender_key), \n\tCONSTRAINT fk_voucher_tender_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_tender_account FOREIGN KEY(tenant_id, company_id, revision_id, line_key) REFERENCES voucher_account_detail (tenant_id, company_id, revision_id, line_key), \n\tCONSTRAINT ck_voucher_tender_voucher_tender_c0 CHECK (amount > 0),\n\tINDEX ix_voucher_tender_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_tender")
