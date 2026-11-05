"""invoice_tax_component; one atomic CREATE."""
from alembic import op

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE invoice_tax_component (\n\tinvoice_id BINARY(16) NOT NULL, \n\tsupply_id BINARY(16) NOT NULL, \n\tcomponent_key VARCHAR(100) NOT NULL, \n\tcode VARCHAR(5) NOT NULL, \n\tbasis NUMERIC(19, 4) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\tpercentage NUMERIC(19, 8) NOT NULL, \n\tsupplier_charged BOOL NOT NULL, \n\trounding_mode VARCHAR(10) NOT NULL, \n\tsource_version INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_tax_component PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_tax_component_supply_id FOREIGN KEY(tenant_id, company_id, invoice_id, supply_id) REFERENCES invoice_supply_fact (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT uq_invoice_tax_component_tenant_id_company_id_invoice_id_94e8 UNIQUE (tenant_id, company_id, invoice_id, supply_id, component_key), \n\tCONSTRAINT ck_invoice_tax_component_code CHECK (code IN ('CGST','SGST','UTGST','IGST','CESS')), \n\tCONSTRAINT ck_invoice_tax_component_amounts CHECK (basis >= 0 AND amount >= 0 AND percentage >= 0), \n\tCONSTRAINT uq_invoice_tax_component_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_tax_component_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_tax_component_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_tax_component_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_tax_component")
