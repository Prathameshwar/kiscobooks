"""Create account_group; exactly one DDL statement in each direction."""
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account_group (\n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\thead_id BINARY(16) NOT NULL, \n\tparent_id BINARY(16), \n\tsystem_key VARCHAR(60), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_group PRIMARY KEY (id), \n\tCONSTRAINT fk_account_group_head_id FOREIGN KEY(tenant_id, company_id, head_id) REFERENCES account_head (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_group_account_group_version CHECK (row_version > 0), \n\tCONSTRAINT fk_account_group_parent_id FOREIGN KEY(tenant_id, company_id, parent_id) REFERENCES account_group (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_group_1 UNIQUE (tenant_id, company_id, system_key), \n\tCONSTRAINT uq_account_group_0 UNIQUE (tenant_id, company_id, code), \n\tCONSTRAINT ck_account_group_account_group_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT uq_account_group_scope UNIQUE (tenant_id, company_id, id),\n\tKEY ix_account_group_name (tenant_id, company_id, name, id),\n\tKEY ix_account_group_page (tenant_id, company_id, id),\n\tKEY ix_account_group_ref0 (tenant_id, company_id, head_id),\n\tKEY ix_account_group_ref1 (tenant_id, company_id, parent_id),\n\tKEY ix_account_group_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_group")
