"""invoice_component_fact; one atomic CREATE."""
from alembic import op

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE invoice_component_fact (\n\tinvoice_id BINARY(16) NOT NULL, \n\tcomponent_key BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tpurpose VARCHAR(20) NOT NULL, \n\tscope VARCHAR(20) NOT NULL, \n\teffect VARCHAR(10) NOT NULL, \n\tinput_kind VARCHAR(20) NOT NULL, \n\tbasis_amount NUMERIC(19, 4) NOT NULL, \n\tbasis_quantity NUMERIC(19, 4), \n\tinput_amount NUMERIC(19, 4) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\taccount_id BINARY(16), \n\tcommercial_treatment VARCHAR(20) NOT NULL, \n\ttax_treatment VARCHAR(20) NOT NULL, \n\treturn_treatment VARCHAR(20) NOT NULL, \n\tsource_evidence VARCHAR(500) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_component_fact PRIMARY KEY (id), \n\tCONSTRAINT uq_invoice_component_fact_tenant_id_company_id_invoice_i_d5f5 UNIQUE (tenant_id, company_id, invoice_id, component_key), \n\tCONSTRAINT fk_invoice_component_fact_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id), \n\tCONSTRAINT ck_invoice_component_fact_basis CHECK (basis_amount >= 0 AND (basis_quantity IS NULL OR basis_quantity >= 0)), \n\tCONSTRAINT uq_invoice_component_fact_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_component_fact_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_component_fact_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_component_fact_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_component_fact")
