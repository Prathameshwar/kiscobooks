"""Create account_head; exactly one DDL statement in each direction."""
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account_head (\n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tnature VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_head PRIMARY KEY (id), \n\tCONSTRAINT ck_account_head_account_head_version CHECK (row_version > 0), \n\tCONSTRAINT ck_account_head_account_head_nature CHECK (nature IN ('ASSET', 'LIABILITY', 'EQUITY', 'INCOME', 'EXPENSE')), \n\tCONSTRAINT uq_account_head_0 UNIQUE (tenant_id, company_id, code), \n\tCONSTRAINT uq_account_head_scope UNIQUE (tenant_id, company_id, id),\n\tKEY ix_account_head_name (tenant_id, company_id, name, id),\n\tKEY ix_account_head_page (tenant_id, company_id, id),\n\tKEY ix_account_head_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_head")
