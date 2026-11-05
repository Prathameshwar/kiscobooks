"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

UP = 'CREATE TABLE voucher_import_revision (\n\ttemplate_id BINARY(16), \n\tjob_id BINARY(16) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tsource_format VARCHAR(10) NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tsnapshot JSON, \n\tcontent MEDIUMBLOB, \n\texpires_at DATETIME(6) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_import_revision PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_import_revision_template FOREIGN KEY(tenant_id, company_id, template_id) REFERENCES import_template_snapshot (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_import_revision_job FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES voucher_import_job (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_import_revision_job UNIQUE (tenant_id, company_id, job_id, id), \n\tCONSTRAINT uq_voucher_import_revision_number UNIQUE (tenant_id, company_id, job_id, revision), \n\tCONSTRAINT uq_voucher_import_revision_scope UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_import_revision_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
DOWN = 'DROP TABLE voucher_import_revision'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
