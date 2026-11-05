"""voucher_charge_target; one atomic CREATE with revision-scoped ownership."""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE voucher_charge_target (\n\trevision_id BINARY(16) NOT NULL, \n\tcharge_id BINARY(16) NOT NULL, \n\tsupply_id BINARY(16) NOT NULL, \n\tpurpose VARCHAR(15) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_charge_target PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_charge_target_supply_id FOREIGN KEY(tenant_id, company_id, revision_id, supply_id) REFERENCES voucher_supply_detail (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT uq_voucher_charge_target_tenant_id_company_id_revision_id_id UNIQUE (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT ck_voucher_charge_target_voucher_charge_target_purpose CHECK (purpose IN ('BASIS','STOCK_COST')), \n\tCONSTRAINT uq_voucher_charge_target_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_charge_target_tenant_id_company_id_revision_i_c970 UNIQUE (tenant_id, company_id, revision_id, charge_id, purpose, supply_id), \n\tCONSTRAINT fk_voucher_charge_target_charge_id FOREIGN KEY(tenant_id, company_id, revision_id, charge_id) REFERENCES voucher_charge_detail (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT fk_voucher_charge_target_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\n\tINDEX ix_voucher_charge_target_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_charge_target")
