"""Create voucher_number_series; one DDL statement in each direction."""
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_number_series (\n\tcode VARCHAR(20) NOT NULL, \n\tprefix VARCHAR(20) NOT NULL, \n\tpadding INTEGER NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_number_series PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_number_series_tenant_id_company_id_code UNIQUE (tenant_id, company_id, code), \n\tCONSTRAINT uq_voucher_number_series_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_number_series_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_number_series")
