"""Create accounting_setup; exactly one DDL statement in each direction."""
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE accounting_setup (\n\tbase_currency VARCHAR(3) NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\ttemplate_version VARCHAR(30), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_accounting_setup PRIMARY KEY (id), \n\tCONSTRAINT uq_accounting_setup_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_accounting_setup_0 UNIQUE (tenant_id, company_id), \n\tCONSTRAINT ck_accounting_setup_accounting_setup_version CHECK (row_version > 0),\n\tKEY ix_accounting_setup_page (tenant_id, company_id, id),\n\tKEY ix_accounting_setup_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE accounting_setup")
