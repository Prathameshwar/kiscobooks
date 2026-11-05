"""voucher_execution; one atomic CREATE, isolated service-owned evidence."""
from alembic import op

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_execution (\n\tsource_guard_id BINARY(16) NOT NULL, \n\texecution_id BINARY(16) NOT NULL, \n\toperation_id BINARY(16) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\tcommand JSON NOT NULL, \n\tresult JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_execution PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_execution_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_execution_identity UNIQUE (tenant_id, company_id, execution_id), \n\tCONSTRAINT uq_voucher_operation_identity UNIQUE (tenant_id, company_id, operation_id), \n\tCONSTRAINT fk_execution_source_guard FOREIGN KEY(tenant_id, company_id, source_guard_id) REFERENCES voucher_source_guard (tenant_id, company_id, id),\n\tINDEX ix_voucher_execution_source (tenant_id, company_id, source_guard_id, id),\n\tINDEX ix_voucher_execution_tenant_id (tenant_id)\n)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_execution")
