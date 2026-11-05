"""Create party_tax_registration; exactly one DDL statement in each direction."""
from alembic import op

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_tax_registration (\n\tparty_id BINARY(16) NOT NULL, \n\tscheme VARCHAR(40) NOT NULL, \n\tregistration_number VARCHAR(80) NOT NULL, \n\tregistration_type VARCHAR(40) NOT NULL, \n\tcountry_code VARCHAR(2) NOT NULL, \n\tstate_code VARCHAR(20), \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_tax_registration PRIMARY KEY (id), \n\tCONSTRAINT uq_party_tax_registration_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_tax_registration_party_tax_registration_version CHECK (row_version > 0), \n\tCONSTRAINT fk_party_tax_registration_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_tax_registration_party_tax_registration_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT uq_party_tax_registration_0 UNIQUE (tenant_id, company_id, party_id, scheme, registration_number, valid_from), \n\tCONSTRAINT ck_party_tax_registration_party_tax_registration_scheme CHECK (scheme IN ('GST_IN', 'VAT', 'OTHER')), \n\tCONSTRAINT ck_party_tax_registration_party_tax_registration_registr_dbc8 CHECK (registration_type IN ('REGULAR', 'COMPOSITION', 'UNREGISTERED', 'OTHER')),\n\tKEY ix_party_tax_registration_page (tenant_id, company_id, id),\n\tKEY ix_party_tax_registration_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_tax_registration")
