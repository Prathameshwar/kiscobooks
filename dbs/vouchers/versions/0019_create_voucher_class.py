"""Create voucher_class; one DDL statement in each direction."""
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_class (\n\ttype_revision_id BINARY(16) NOT NULL, \n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(120) NOT NULL, \n\tpolicy JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_class PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_class_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_class_tenant_id_company_id_type_revision_id_code UNIQUE (tenant_id, company_id, type_revision_id, code), \n\tCONSTRAINT fk_voucher_class_1 FOREIGN KEY(tenant_id, company_id, type_revision_id) REFERENCES voucher_type_revision (tenant_id, company_id, id),\n\tKEY ix_voucher_class_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_class")
