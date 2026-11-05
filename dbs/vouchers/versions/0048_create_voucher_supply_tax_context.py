"""Line tax context; one atomic CREATE with revision-scoped ownership."""

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE voucher_supply_tax_context (\n\trevision_id BINARY(16) NOT NULL, \n\tsupply_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tdate_contract_version INTEGER NOT NULL, \n\tprofile VARCHAR(40) NOT NULL, \n\tcompany_registration_id BINARY(16), \n\tparty_registration_id BINARY(16), \n\tplace_of_supply VARCHAR(10), \n\tservice_completion_date DATE, \n\tpayment_date DATE, \n\tsupplier_invoice_number VARCHAR(120), \n\tsupplier_invoice_date DATE, \n\twithholding_section_id BINARY(16), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_supply_tax_context PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_supply_tax_context_supply_id FOREIGN KEY(tenant_id, company_id, revision_id, supply_id) REFERENCES voucher_supply_detail (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT uq_voucher_supply_tax_context_tenant_id_company_id_revis_007a UNIQUE (tenant_id, company_id, revision_id, supply_id), \n\tCONSTRAINT ck_voucher_supply_tax_context_date_version CHECK (date_contract_version = 2), \n\tCONSTRAINT ck_voucher_supply_tax_context_profile CHECK (profile IN ('UNTAXED_ACCOUNT','INDIA_DOMESTIC_SERVICE','INDIA_DOMESTIC_SERVICE_RCM')), \n\tCONSTRAINT uq_voucher_supply_tax_context_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_supply_tax_context_tenant_id_company_id_revis_c016 UNIQUE (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT fk_voucher_supply_tax_context_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\nINDEX ix_voucher_supply_tax_context_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_supply_tax_context")
