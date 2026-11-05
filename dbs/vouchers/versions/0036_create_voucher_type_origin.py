"""voucher_type_origin; one atomic CREATE including scoped indexes."""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_type_origin (\n\ttype_id BINARY(16) NOT NULL, \n\tsource_revision_id BINARY(16) NOT NULL, \n\tsource_content_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_type_origin PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_type_origin_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_type_origin_tenant_id_company_id_type_id UNIQUE (tenant_id, company_id, type_id), \n\tCONSTRAINT fk_voucher_type_origin_child FOREIGN KEY(tenant_id, company_id, type_id) REFERENCES voucher_type (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_type_origin_source FOREIGN KEY(tenant_id, company_id, source_revision_id) REFERENCES voucher_type_revision (tenant_id, company_id, id),\n\tINDEX ix_voucher_type_origin_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_type_origin")
