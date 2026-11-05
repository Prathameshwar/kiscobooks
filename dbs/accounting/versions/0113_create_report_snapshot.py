"""report_snapshot; one atomic DDL statement."""
from alembic import op

revision = '0113'
down_revision = '0112'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_snapshot (\n\tmanifest JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_snapshot PRIMARY KEY (id), \n\tCONSTRAINT uq_report_snapshot_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_snapshot_report_snapshot_version CHECK (row_version > 0),\n\tINDEX ix_report_snapshot_page (tenant_id, company_id, id),\n\tINDEX ix_report_snapshot_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_snapshot")
