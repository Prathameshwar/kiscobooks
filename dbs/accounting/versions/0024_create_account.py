"""Create account; exactly one DDL statement in each direction."""
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account (\n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tgroup_id BINARY(16) NOT NULL, \n\tkind VARCHAR(40) NOT NULL, \n\tparty_id BINARY(16), \n\tparty_role VARCHAR(40), \n\tcurrency_mode VARCHAR(40) NOT NULL, \n\tcurrency VARCHAR(3), \n\tposting_policy VARCHAR(40) NOT NULL, \n\tdescription VARCHAR(500), \n\tsystem_key VARCHAR(60), \n\tused_at DATETIME(6), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account PRIMARY KEY (id), \n\tCONSTRAINT uq_account_1 UNIQUE (tenant_id, company_id, system_key), \n\tCONSTRAINT ck_account_account_currency_mode CHECK (currency_mode IN ('BASE', 'FIXED', 'MULTI')), \n\tCONSTRAINT ck_account_account_version CHECK (row_version > 0), \n\tCONSTRAINT ck_account_account_party_role CHECK (party_role IN ('CUSTOMER', 'SUPPLIER', 'OTHER')), \n\tCONSTRAINT fk_account_group_id FOREIGN KEY(tenant_id, company_id, group_id) REFERENCES account_group (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_account_posting_policy CHECK (posting_policy IN ('MANUAL_ALLOWED', 'SOURCE_ONLY')), \n\tCONSTRAINT ck_account_account_kind CHECK (kind IN ('GENERAL', 'CASH', 'BANK', 'PARTY', 'TAX', 'INVENTORY_CONTROL', 'ASSET_CONTROL')), \n\tCONSTRAINT fk_account_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_0 UNIQUE (tenant_id, company_id, code), \n\tCONSTRAINT ck_account_account_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),\n\tKEY ix_account_name (tenant_id, company_id, name, id),\n\tKEY ix_account_page (tenant_id, company_id, id),\n\tKEY ix_account_ref0 (tenant_id, company_id, group_id),\n\tKEY ix_account_ref1 (tenant_id, company_id, party_id),\n\tKEY ix_account_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account")
