"""report_source_claim; one atomic DDL statement."""
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_source_claim (\n\tentity VARCHAR(40) NOT NULL, \n\tsource_id BINARY(16) NOT NULL, \n\tfinancial_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_source_claim PRIMARY KEY (id), \n\tCONSTRAINT uq_report_source_claim_identity UNIQUE (tenant_id, company_id, entity, source_id), \n\tCONSTRAINT uq_report_source_claim_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_source_claim_report_source_claim_version CHECK (row_version > 0),\n\tINDEX ix_report_source_claim_page (tenant_id, company_id, id),\n\tINDEX ix_report_source_claim_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_source_claim")
