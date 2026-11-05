"""Create party_identifier; exactly one DDL statement in each direction."""
from alembic import op

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_identifier (\n\tparty_id BINARY(16) NOT NULL, \n\tscheme VARCHAR(40) NOT NULL, \n\tvalue VARCHAR(80) NOT NULL, \n\tcountry_code VARCHAR(2) NOT NULL, \n\tverification_reference VARCHAR(160), \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_identifier PRIMARY KEY (id), \n\tCONSTRAINT uq_party_identifier_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_identifier_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_identifier_party_identifier_version CHECK (row_version > 0), \n\tCONSTRAINT ck_party_identifier_party_identifier_scheme CHECK (scheme IN ('PAN', 'TAN', 'CIN', 'EIN', 'UDYAM', 'BUSINESS_REGISTRATION')), \n\tCONSTRAINT ck_party_identifier_party_identifier_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT uq_party_identifier_0 UNIQUE (tenant_id, company_id, party_id, scheme, valid_from),\n\tKEY ix_party_identifier_page (tenant_id, company_id, id),\n\tKEY ix_party_identifier_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_identifier")
