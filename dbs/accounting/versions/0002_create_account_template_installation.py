"""Create account_template_installation; exactly one DDL statement in each direction."""
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE account_template_installation (\n\ttemplate_key VARCHAR(60) NOT NULL, \n\ttemplate_version VARCHAR(30) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_template_installation PRIMARY KEY (id), \n\tCONSTRAINT uq_account_template_installation_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_account_template_installation_account_template_instal_2830 CHECK (row_version > 0), \n\tCONSTRAINT uq_account_template_installation_0 UNIQUE (tenant_id, company_id, template_key, template_version),\n\tKEY ix_account_template_installation_page (tenant_id, company_id, id),\n\tKEY ix_account_template_installation_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_template_installation")
