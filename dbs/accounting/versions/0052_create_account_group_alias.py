"""create account group alias; one DDL statement per direction."""
from alembic import op

revision = '0052'
down_revision = '0051'
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE account_group_alias (\n\tgroup_id BINARY(16) NOT NULL, \n\talias VARCHAR(160) NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_group_alias PRIMARY KEY (id), \n\tCONSTRAINT fk_account_group_alias_group_id FOREIGN KEY(tenant_id, company_id, group_id) REFERENCES account_group (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_group_alias_account_group_alias_version CHECK (row_version > 0), \n\tCONSTRAINT ck_account_group_alias_account_group_alias_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT uq_account_group_alias_0 UNIQUE (tenant_id, company_id, alias), \n\tCONSTRAINT uq_account_group_alias_scope UNIQUE (tenant_id, company_id, id),\n\tKEY ix_account_group_alias_page (tenant_id, company_id, id),\n\tKEY ix_account_group_alias_ref0 (tenant_id, company_id, group_id),\n\tKEY ix_account_group_alias_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"
DOWNGRADE = 'DROP TABLE account_group_alias'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
