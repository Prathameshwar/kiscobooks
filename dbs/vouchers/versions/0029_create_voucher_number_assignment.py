"""Create voucher_number_assignment; one DDL statement in each direction."""
from alembic import op

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_number_assignment (\n\tseries_id BINARY(16) NOT NULL, \n\trevision_id BINARY(16) NOT NULL, \n\tfiscal_start_date DATE NOT NULL, \n\tsequence BIGINT NOT NULL, \n\tdisplay_number VARCHAR(100) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_number_assignment PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_number_assignment_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_number_assignment_2 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_number_assignment_tenant_id_company_id_series_2739 UNIQUE (tenant_id, company_id, series_id, fiscal_start_date, sequence), \n\tCONSTRAINT fk_voucher_number_assignment_1 FOREIGN KEY(tenant_id, company_id, series_id) REFERENCES voucher_number_series (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_number_assignment_tenant_id_company_id_revision_id UNIQUE (tenant_id, company_id, revision_id),\n\tKEY ix_voucher_number_assignment_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_number_assignment")
