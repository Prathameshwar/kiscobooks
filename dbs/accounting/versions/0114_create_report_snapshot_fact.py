"""report_snapshot_fact; one atomic DDL statement."""
from alembic import op

revision = '0114'
down_revision = '0113'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_snapshot_fact (\n\tsnapshot_id BINARY(16) NOT NULL, \n\tordinal BIGINT NOT NULL, \n\tfact JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_snapshot_fact PRIMARY KEY (id), \n\tCONSTRAINT uq_report_snapshot_fact_ordinal UNIQUE (tenant_id, company_id, snapshot_id, ordinal), \n\tCONSTRAINT uq_report_snapshot_fact_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_snapshot_fact_report_snapshot_fact_version CHECK (row_version > 0), \n\tCONSTRAINT fk_report_snapshot_fact_snapshot_id FOREIGN KEY(tenant_id, company_id, snapshot_id) REFERENCES report_snapshot (tenant_id, company_id, id),\n\tINDEX ix_report_snapshot_fact_page (tenant_id, company_id, id),\n\tINDEX ix_report_snapshot_fact_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_snapshot_fact")
