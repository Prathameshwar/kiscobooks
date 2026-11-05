"""Create voucher_type_section; one DDL statement in each direction."""
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_type_section (\n\ttype_revision_id BINARY(16) NOT NULL, \n\tsection VARCHAR(40) NOT NULL, \n\trequirement VARCHAR(20) NOT NULL, \n\tminimum_stage VARCHAR(20) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_type_section PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_type_section_tenant_id_company_id_type_revisi_4695 UNIQUE (tenant_id, company_id, type_revision_id, section), \n\tCONSTRAINT uq_voucher_type_section_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_type_section_1 FOREIGN KEY(tenant_id, company_id, type_revision_id) REFERENCES voucher_type_revision (tenant_id, company_id, id),\n\tKEY ix_voucher_type_section_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_type_section")
