"""report_definition; one atomic DDL statement."""
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_definition (\n\tcode VARCHAR(40) NOT NULL, \n\tversion INTEGER NOT NULL, \n\trule_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_definition PRIMARY KEY (id), \n\tCONSTRAINT ck_report_definition_report_definition_version CHECK (row_version > 0), \n\tCONSTRAINT uq_report_definition_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_report_definition_version UNIQUE (tenant_id, company_id, code, version),\n\tINDEX ix_report_definition_page (tenant_id, company_id, id),\n\tINDEX ix_report_definition_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_definition")
