"""voucher_financial_detail; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_financial_detail (\n\trevision_id BINARY(16) NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\tpurpose VARCHAR(30) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_financial_detail PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_financial_detail_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_financial_detail_tenant_id_company_id_revision_id UNIQUE (tenant_id, company_id, revision_id), \n\tCONSTRAINT fk_voucher_financial_detail_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\n\tINDEX ix_voucher_financial_detail_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_financial_detail")
