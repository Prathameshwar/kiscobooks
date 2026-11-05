"""report_company; one atomic DDL statement."""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_company (\n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_company PRIMARY KEY (id), \n\tCONSTRAINT uq_report_company_identity UNIQUE (tenant_id, company_id), \n\tCONSTRAINT ck_report_company_report_company_version CHECK (row_version > 0), \n\tCONSTRAINT uq_report_company_scope UNIQUE (tenant_id, company_id, id),\n\tINDEX ix_report_company_page (tenant_id, company_id, id),\n\tINDEX ix_report_company_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_company")
