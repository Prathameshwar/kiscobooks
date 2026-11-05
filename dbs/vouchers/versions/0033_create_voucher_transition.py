"""Create voucher_transition; one DDL statement in each direction."""
from alembic import op

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_transition (\n\tvoucher_id BINARY(16) NOT NULL, \n\trevision_id BINARY(16) NOT NULL, \n\taction VARCHAR(30) NOT NULL, \n\tfrom_status VARCHAR(20) NOT NULL, \n\tto_status VARCHAR(20) NOT NULL, \n\treason VARCHAR(500) NOT NULL, \n\tvoucher_version INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_transition PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_transition_1 FOREIGN KEY(tenant_id, company_id, voucher_id) REFERENCES voucher (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_transition_2 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_transition_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_transition_0 (tenant_id, company_id, voucher_id, id),\n\tKEY ix_voucher_transition_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_transition")
