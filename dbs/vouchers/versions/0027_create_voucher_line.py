"""Create voucher_line; one DDL statement in each direction."""
from alembic import op

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_line (\n\trevision_id BINARY(16) NOT NULL, \n\tline_key BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tline_kind VARCHAR(20) NOT NULL, \n\tdescription VARCHAR(1000) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_line PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_line_tenant_id_company_id_revision_id_sequence UNIQUE (tenant_id, company_id, revision_id, sequence), \n\tCONSTRAINT uq_voucher_line_tenant_id_company_id_revision_id_line_key UNIQUE (tenant_id, company_id, revision_id, line_key), \n\tCONSTRAINT fk_voucher_line_1 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_line_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_line_tenant_id_company_id_revision_id_id UNIQUE (tenant_id, company_id, revision_id, id),\n\tKEY ix_voucher_line_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_line")
