"""Create account_alias; exactly one DDL statement in each direction."""
from alembic import op

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account_alias (\n\taccount_id BINARY(16) NOT NULL, \n\talias VARCHAR(160) NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_alias PRIMARY KEY (id), \n\tCONSTRAINT uq_account_alias_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_alias_account_alias_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT uq_account_alias_0 UNIQUE (tenant_id, company_id, alias), \n\tCONSTRAINT ck_account_alias_account_alias_version CHECK (row_version > 0), \n\tCONSTRAINT fk_account_alias_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),\n\tKEY ix_account_alias_page (tenant_id, company_id, id),\n\tKEY ix_account_alias_ref0 (tenant_id, company_id, account_id),\n\tKEY ix_account_alias_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_alias")
