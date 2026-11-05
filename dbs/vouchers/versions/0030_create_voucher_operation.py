"""voucher_operation; one atomic CREATE including scoped indexes."""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_operation (\n\tvoucher_id BINARY(16) NOT NULL, \n\trevision_id BINARY(16) NOT NULL, \n\texecution_id BINARY(16) NOT NULL, \n\tpurpose VARCHAR(30) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\tcommand JSON, \n\tcancel_requested BOOL NOT NULL, \n\tattempt_count INTEGER NOT NULL, \n\tresult JSON, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_operation PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_operation_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_operation_tenant_id_company_id_execution_id UNIQUE (tenant_id, company_id, execution_id), \n\tCONSTRAINT fk_voucher_operation_1 FOREIGN KEY(tenant_id, company_id, voucher_id) REFERENCES voucher (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_operation_2 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\n\tINDEX ix_voucher_operation_0 (tenant_id, company_id, status, id),\n\tINDEX ix_voucher_operation_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_operation")
