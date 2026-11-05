"""Create voucher_type_revision; one DDL statement in each direction."""
from alembic import op

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_type_revision (\n\ttype_id BINARY(16) NOT NULL, \n\trevision_number INTEGER NOT NULL, \n\tpolicy JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_type_revision PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_type_revision_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_type_revision_tenant_id_company_id_type_id_re_386d UNIQUE (tenant_id, company_id, type_id, revision_number), \n\tCONSTRAINT fk_voucher_type_revision_1 FOREIGN KEY(tenant_id, company_id, type_id) REFERENCES voucher_type (tenant_id, company_id, id),\n\tKEY ix_voucher_type_revision_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_type_revision")
