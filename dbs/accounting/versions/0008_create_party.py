"""Create party; exactly one DDL statement in each direction."""
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party (\n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tlegal_name VARCHAR(200) NOT NULL, \n\tparty_type VARCHAR(40) NOT NULL, \n\tcountry_code VARCHAR(2) NOT NULL, \n\tnotes VARCHAR(1000), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party PRIMARY KEY (id), \n\tCONSTRAINT uq_party_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_party_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT ck_party_party_version CHECK (row_version > 0), \n\tCONSTRAINT ck_party_party_party_type CHECK (party_type IN ('ORGANISATION', 'PERSON')), \n\tCONSTRAINT uq_party_0 UNIQUE (tenant_id, company_id, code),\n\tKEY ix_party_name (tenant_id, company_id, name, id),\n\tKEY ix_party_page (tenant_id, company_id, id),\n\tKEY ix_party_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party")
