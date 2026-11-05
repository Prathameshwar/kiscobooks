"""Create account_external_key; exactly one DDL statement in each direction."""
from alembic import op

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account_external_key (\n\taccount_id BINARY(16) NOT NULL, \n\tsource_namespace VARCHAR(80) NOT NULL, \n\texternal_key VARCHAR(160) NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_external_key PRIMARY KEY (id), \n\tCONSTRAINT ck_account_external_key_account_external_key_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT ck_account_external_key_account_external_key_version CHECK (row_version > 0), \n\tCONSTRAINT fk_account_external_key_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_external_key_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_external_key_0 UNIQUE (tenant_id, company_id, source_namespace, external_key),\n\tKEY ix_account_external_key_page (tenant_id, company_id, id),\n\tKEY ix_account_external_key_ref0 (tenant_id, company_id, account_id),\n\tKEY ix_account_external_key_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_external_key")
