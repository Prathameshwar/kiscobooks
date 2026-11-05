"""Create voucher_number_counter; one DDL statement in each direction."""
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_number_counter (\n\tseries_id BINARY(16) NOT NULL, \n\tfiscal_start_date DATE NOT NULL, \n\tnext_value BIGINT NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_number_counter PRIMARY KEY (id), \n\tCONSTRAINT ck_voucher_number_counter_positive CHECK (next_value > 0), \n\tCONSTRAINT uq_voucher_number_counter_tenant_id_company_id_series_id_8f81 UNIQUE (tenant_id, company_id, series_id, fiscal_start_date), \n\tCONSTRAINT fk_voucher_number_counter_1 FOREIGN KEY(tenant_id, company_id, series_id) REFERENCES voucher_number_series (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_number_counter_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_number_counter_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_number_counter")
