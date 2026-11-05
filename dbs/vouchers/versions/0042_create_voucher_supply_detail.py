"""voucher_supply_detail; one atomic CREATE with revision-scoped ownership."""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE voucher_supply_detail (\n\trevision_id BINARY(16) NOT NULL, \n\tline_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\taccount_id BINARY(16) NOT NULL, \n\taccount_version INTEGER NOT NULL, \n\tsupply_kind VARCHAR(10) NOT NULL, \n\tdescription VARCHAR(1000) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\tprice_basis VARCHAR(20) NOT NULL, \n\titem_line_key BINARY(16), \n\tunit_price NUMERIC(19, 4), \n\tprice_denominator NUMERIC(19, 4) NOT NULL, \n\tfree_purpose VARCHAR(30) NOT NULL, \n\tfree_reason VARCHAR(500), \n\tpromotion_revision_id BINARY(16), \n\tpromotion_version INTEGER, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_supply_detail PRIMARY KEY (id), \n\tCONSTRAINT ck_voucher_supply_detail_voucher_supply_amounts CHECK (amount >= 0 AND price_denominator > 0 AND (unit_price IS NULL OR unit_price >= 0)), \n\tCONSTRAINT fk_voucher_supply_detail_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_supply_detail_line_id FOREIGN KEY(tenant_id, company_id, revision_id, line_id) REFERENCES voucher_line (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT ck_voucher_supply_detail_voucher_supply_promotion CHECK ((promotion_revision_id IS NULL AND promotion_version IS NULL) OR (promotion_revision_id IS NOT NULL AND promotion_version IS NOT NULL AND promotion_version > 0)), \n\tCONSTRAINT uq_voucher_supply_detail_tenant_id_company_id_revision_id_id UNIQUE (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT uq_voucher_supply_detail_tenant_id_company_id_revision_i_e789 UNIQUE (tenant_id, company_id, revision_id, line_id), \n\tCONSTRAINT ck_voucher_supply_detail_voucher_supply_version CHECK (account_version > 0 AND sequence > 0), \n\tCONSTRAINT uq_voucher_supply_detail_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_supply_detail_tenant_id_company_id_revision_i_0391 UNIQUE (tenant_id, company_id, revision_id, sequence), \n\tCONSTRAINT ck_voucher_supply_detail_voucher_supply_kind CHECK (supply_kind IN ('ACCOUNT','SERVICE','GOODS')), \n\tCONSTRAINT ck_voucher_supply_detail_voucher_supply_price_basis CHECK (price_basis IN ('NET_EXCL_TAX','GROSS_INCL_TAX')),\n\tINDEX ix_voucher_supply_detail_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_supply_detail")
