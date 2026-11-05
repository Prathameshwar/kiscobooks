"""report_bundle; one atomic DDL statement."""
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE report_bundle (\n\tgeneration_id BINARY(16) NOT NULL, \n\tsource_id BINARY(16) NOT NULL, \n\tmanifest JSON NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tlast_ordinal BIGINT NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_bundle PRIMARY KEY (id), \n\tCONSTRAINT ck_report_bundle_report_bundle_version CHECK (row_version > 0), \n\tCONSTRAINT uq_report_bundle_source UNIQUE (tenant_id, company_id, generation_id, source_id), \n\tCONSTRAINT uq_report_bundle_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_report_bundle_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id), \n\tCONSTRAINT ck_report_bundle_report_bundle_valid CHECK (status IN ('STAGING','APPLIED') AND last_ordinal >= 0),\n\tINDEX ix_report_bundle_page (tenant_id, company_id, id),\n\tINDEX ix_report_bundle_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_bundle")
