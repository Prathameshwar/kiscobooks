"""report_generation; one atomic DDL statement."""
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE report_generation (\n\tstatus VARCHAR(20) NOT NULL, \n\tsnapshot_id BINARY(16) NOT NULL, \n\tapplied_sequence BIGINT NOT NULL, \n\ttarget_sequence BIGINT, \n\tmanifest JSON, \n\tfailure_code VARCHAR(60), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_generation PRIMARY KEY (id), \n\tCONSTRAINT ck_report_generation_report_generation_version CHECK (row_version > 0), \n\tCONSTRAINT ck_report_generation_report_generation_valid CHECK (status IN ('PENDING','BUILDING','READY','QUARANTINED') AND applied_sequence >= 0), \n\tCONSTRAINT uq_report_generation_scope UNIQUE (tenant_id, company_id, id),\n\tINDEX ix_report_generation_page (tenant_id, company_id, id),\n\tINDEX ix_report_generation_tenant_id (tenant_id),\n\tINDEX ix_report_generation_work (tenant_id, company_id, status, id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_generation")
