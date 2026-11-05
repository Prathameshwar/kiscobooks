"""Create voucher_reference; one DDL statement in each direction."""
from alembic import op

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_reference (\n\trevision_id BINARY(16) NOT NULL, \n\tpurpose VARCHAR(30) NOT NULL, \n\treference VARCHAR(120) NOT NULL, \n\treference_date DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_reference PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_reference_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_reference_1 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\n\tKEY ix_voucher_reference_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_reference")
