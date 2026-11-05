"""voucher_supply_quantity; one atomic CREATE with revision-scoped ownership."""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE voucher_supply_quantity (\n\trevision_id BINARY(16) NOT NULL, \n\tsupply_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tbasis VARCHAR(10) NOT NULL, \n\tquantity NUMERIC(19, 4) NOT NULL, \n\tunit_id BINARY(16) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_supply_quantity PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_supply_quantity_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_supply_quantity_tenant_id_company_id_revision_ba51 UNIQUE (tenant_id, company_id, revision_id, supply_id, basis), \n\tCONSTRAINT ck_voucher_supply_quantity_voucher_supply_quantity_basis CHECK (basis IN ('ACTUAL','BILLED','ACCEPTED','RETURNED','MEASURED')), \n\tCONSTRAINT uq_voucher_supply_quantity_tenant_id_company_id_revision_id_id UNIQUE (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT ck_voucher_supply_quantity_voucher_supply_quantity_amount CHECK (quantity >= 0), \n\tCONSTRAINT fk_voucher_supply_quantity_supply_id FOREIGN KEY(tenant_id, company_id, revision_id, supply_id) REFERENCES voucher_supply_detail (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT uq_voucher_supply_quantity_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tINDEX ix_voucher_supply_quantity_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_supply_quantity")
