"""Create account_group_closure; exactly one DDL statement in each direction."""
from alembic import op

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE account_group_closure (\n\tancestor_id BINARY(16) NOT NULL, \n\tdescendant_id BINARY(16) NOT NULL, \n\tdepth INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_group_closure PRIMARY KEY (id), \n\tCONSTRAINT uq_account_group_closure_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_account_group_closure_descendant_id FOREIGN KEY(tenant_id, company_id, descendant_id) REFERENCES account_group (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_group_closure_account_group_closure_version CHECK (row_version > 0), \n\tCONSTRAINT fk_account_group_closure_ancestor_id FOREIGN KEY(tenant_id, company_id, ancestor_id) REFERENCES account_group (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_group_closure_0 UNIQUE (tenant_id, company_id, ancestor_id, descendant_id),\n\tKEY ix_account_group_closure_page (tenant_id, company_id, id),\n\tKEY ix_account_group_closure_ref1 (tenant_id, company_id, descendant_id),\n\tKEY ix_account_group_closure_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_group_closure")
