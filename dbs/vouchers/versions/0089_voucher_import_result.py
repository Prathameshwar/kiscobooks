"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

UP = 'CREATE TABLE voucher_import_result (\n\tattempt_id BINARY(16) NOT NULL, \n\trecord_key VARCHAR(64) NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tresult JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_import_result PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_import_result_attempt FOREIGN KEY(tenant_id, company_id, attempt_id) REFERENCES voucher_import_attempt (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_import_result_key UNIQUE (tenant_id, company_id, attempt_id, record_key),\n\tKEY ix_voucher_import_result_page (tenant_id, company_id, attempt_id, ordinal, id),\n\tKEY ix_voucher_import_result_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
DOWN = 'DROP TABLE voucher_import_result'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
