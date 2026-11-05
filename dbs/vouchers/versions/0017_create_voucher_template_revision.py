"""Create voucher_template_revision; one DDL statement in each direction."""
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_template_revision (\n\ttemplate_id BINARY(16) NOT NULL, \n\trevision_number INTEGER NOT NULL, \n\ttitle VARCHAR(120) NOT NULL, \n\tfields JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_template_revision PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_template_revision_1 FOREIGN KEY(tenant_id, company_id, template_id) REFERENCES voucher_template (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_template_revision_tenant_id_company_id_templa_23f2 UNIQUE (tenant_id, company_id, template_id, revision_number), \n\tCONSTRAINT uq_voucher_template_revision_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_template_revision_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_template_revision")
