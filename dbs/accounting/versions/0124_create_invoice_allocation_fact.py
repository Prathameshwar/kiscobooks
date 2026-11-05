"""invoice_allocation_fact; one atomic CREATE."""
from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE invoice_allocation_fact (\n\tinvoice_id BINARY(16) NOT NULL, \n\tcomponent_id BINARY(16) NOT NULL, \n\tsupply_id BINARY(16) NOT NULL, \n\tpurpose VARCHAR(20) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_allocation_fact PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_allocation_fact_component_id FOREIGN KEY(tenant_id, company_id, invoice_id, component_id) REFERENCES invoice_component_fact (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_allocation_fact_supply_id FOREIGN KEY(tenant_id, company_id, invoice_id, supply_id) REFERENCES invoice_supply_fact (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT uq_invoice_allocation_fact_tenant_id_company_id_invoice__7504 UNIQUE (tenant_id, company_id, invoice_id, component_id, supply_id, purpose), \n\tCONSTRAINT ck_invoice_allocation_fact_purpose CHECK (purpose IN ('COMMERCIAL','TAX_BASE','STOCK_COST')), \n\tCONSTRAINT uq_invoice_allocation_fact_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_allocation_fact_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_allocation_fact_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_allocation_fact_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_allocation_fact")
