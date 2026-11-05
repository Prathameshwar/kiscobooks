"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

UP = 'CREATE TABLE voucher_import_attempt (\n\tjob_id BINARY(16) NOT NULL, \n\trevision_id BINARY(16) NOT NULL, \n\tphase VARCHAR(10) NOT NULL, \n\toutcome VARCHAR(20) NOT NULL, \n\tfinished_at DATETIME(6), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_import_attempt PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_import_attempt_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_import_attempt_job FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES voucher_import_job (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_import_attempt_revision FOREIGN KEY(tenant_id, company_id, job_id, revision_id) REFERENCES voucher_import_revision (tenant_id, company_id, job_id, id),\n\tKEY ix_voucher_import_attempt_job (tenant_id, company_id, job_id, id),\n\tKEY ix_voucher_import_attempt_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
DOWN = 'DROP TABLE voucher_import_attempt'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
