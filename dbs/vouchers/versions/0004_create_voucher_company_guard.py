"""Create voucher_company_guard; one DDL statement in each direction."""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_company_guard (\n\tgeneration INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_company_guard PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_company_guard_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_company_guard_tenant_id_company_id UNIQUE (tenant_id, company_id),\n\tKEY ix_voucher_company_guard_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_company_guard")
