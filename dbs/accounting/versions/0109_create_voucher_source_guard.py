"""voucher_source_guard; one atomic CREATE, isolated service-owned evidence."""
from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_source_guard (\n\tvoucher_id BINARY(16) NOT NULL, \n\tcommitted_execution_id BINARY(16), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_source_guard PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_source_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_source_identity UNIQUE (tenant_id, company_id, voucher_id),\n\tINDEX ix_voucher_source_guard_tenant_id (tenant_id)\n)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_source_guard")
