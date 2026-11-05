"""Create party_address; exactly one DDL statement in each direction."""
from alembic import op

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_address (\n\tparty_id BINARY(16) NOT NULL, \n\tlabel VARCHAR(100) NOT NULL, \n\tmailing_name VARCHAR(200) NOT NULL, \n\tline1 VARCHAR(200) NOT NULL, \n\tline2 VARCHAR(200), \n\tlocality VARCHAR(100), \n\tcity VARCHAR(100) NOT NULL, \n\tstate_code VARCHAR(20), \n\tcountry_code VARCHAR(2) NOT NULL, \n\tpostal_code VARCHAR(20), \n\tdelivery_instructions VARCHAR(500), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_address PRIMARY KEY (id), \n\tCONSTRAINT uq_party_address_0 UNIQUE (tenant_id, company_id, party_id, label), \n\tCONSTRAINT uq_party_address_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_address_party_address_version CHECK (row_version > 0), \n\tCONSTRAINT ck_party_address_party_address_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT fk_party_address_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),\n\tKEY ix_party_address_page (tenant_id, company_id, id),\n\tKEY ix_party_address_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_address")
