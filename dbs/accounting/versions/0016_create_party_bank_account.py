"""Create party_bank_account; exactly one DDL statement in each direction."""
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_bank_account (\n\tparty_id BINARY(16) NOT NULL, \n\tlabel VARCHAR(100) NOT NULL, \n\tbeneficiary_name VARCHAR(200) NOT NULL, \n\tbank_name VARCHAR(160) NOT NULL, \n\tcountry_code VARCHAR(2) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\trouting_code VARCHAR(40), \n\taccount_number_ciphertext BLOB(1024) NOT NULL, \n\taccount_number_last4 VARCHAR(4) NOT NULL, \n\tverification_reference VARCHAR(160), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_bank_account PRIMARY KEY (id), \n\tCONSTRAINT uq_party_bank_account_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_bank_account_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_bank_account_party_bank_account_version CHECK (row_version > 0), \n\tCONSTRAINT uq_party_bank_account_0 UNIQUE (tenant_id, company_id, party_id, label), \n\tCONSTRAINT ck_party_bank_account_party_bank_account_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),\n\tKEY ix_party_bank_account_page (tenant_id, company_id, id),\n\tKEY ix_party_bank_account_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_bank_account")
