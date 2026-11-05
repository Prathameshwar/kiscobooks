"""Create party_registration_address; exactly one DDL statement in each direction."""
from alembic import op

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE party_registration_address (\n\tparty_id BINARY(16) NOT NULL, \n\tregistration_id BINARY(16) NOT NULL, \n\taddress_id BINARY(16) NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_registration_address PRIMARY KEY (id), \n\tCONSTRAINT uq_party_registration_address_0 UNIQUE (tenant_id, company_id, registration_id, address_id, valid_from), \n\tCONSTRAINT ck_party_registration_address_party_registration_address_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT fk_party_registration_address_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_registration_address_party_registration_address_version CHECK (row_version > 0), \n\tCONSTRAINT uq_party_registration_address_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_registration_address_registration_id FOREIGN KEY(tenant_id, company_id, registration_id) REFERENCES party_tax_registration (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_registration_address_address_id FOREIGN KEY(tenant_id, company_id, address_id) REFERENCES party_address (tenant_id, company_id, id),\n\tKEY ix_party_registration_address_page (tenant_id, company_id, id),\n\tKEY ix_party_registration_address_ref0 (tenant_id, company_id, address_id),\n\tKEY ix_party_registration_address_ref1 (tenant_id, company_id, party_id),\n\tKEY ix_party_registration_address_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_registration_address")
