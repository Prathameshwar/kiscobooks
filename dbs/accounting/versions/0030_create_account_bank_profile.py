"""Create account_bank_profile; exactly one DDL statement in each direction."""
from alembic import op

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE account_bank_profile (\n\taccount_id BINARY(16) NOT NULL, \n\tcompany_bank_id BINARY(16) NOT NULL, \n\treconciliation_start_date DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_bank_profile PRIMARY KEY (id), \n\tCONSTRAINT uq_account_bank_profile_1 UNIQUE (tenant_id, company_id, company_bank_id), \n\tCONSTRAINT fk_account_bank_profile_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_bank_profile_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_bank_profile_account_bank_profile_version CHECK (row_version > 0), \n\tCONSTRAINT uq_account_bank_profile_0 UNIQUE (tenant_id, company_id, account_id),\n\tKEY ix_account_bank_profile_page (tenant_id, company_id, id),\n\tKEY ix_account_bank_profile_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_bank_profile")
