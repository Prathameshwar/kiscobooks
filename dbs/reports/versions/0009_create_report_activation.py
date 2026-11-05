"""report_activation; one atomic DDL statement."""
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE report_activation (\n\tgeneration_id BINARY(16) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_report_activation PRIMARY KEY (id), \n\tCONSTRAINT ck_report_activation_report_activation_version CHECK (row_version > 0), \n\tCONSTRAINT fk_report_activation_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id), \n\tCONSTRAINT uq_report_activation_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_report_activation_company UNIQUE (tenant_id, company_id),\n\tINDEX ix_report_activation_page (tenant_id, company_id, id),\n\tINDEX ix_report_activation_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_activation")
