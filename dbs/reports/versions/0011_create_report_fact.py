"""report_fact; one atomic DDL statement."""
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_fact (\n\tgeneration_id BINARY(16) NOT NULL, \n\tentity VARCHAR(40) NOT NULL, \n\tsource_id BINARY(16) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tdata JSON, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_fact PRIMARY KEY (id), \n\tCONSTRAINT ck_report_fact_report_fact_version CHECK (row_version > 0), \n\tCONSTRAINT uq_report_fact_source UNIQUE (tenant_id, company_id, generation_id, entity, source_id), \n\tCONSTRAINT uq_report_fact_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_report_fact_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id),\n\tINDEX ix_report_fact_page (tenant_id, company_id, id),\n\tINDEX ix_report_fact_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_fact")
