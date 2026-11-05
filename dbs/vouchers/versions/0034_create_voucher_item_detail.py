"""Create voucher_item_detail; one DDL statement in each direction."""
from alembic import op

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_item_detail (\n\trevision_id BINARY(16) NOT NULL, \n\tline_id BINARY(16) NOT NULL, \n\titem_id BINARY(16) NOT NULL, \n\titem_version INTEGER NOT NULL, \n\tunit_id BINARY(16) NOT NULL, \n\tactual_quantity NUMERIC(19, 4) NOT NULL, \n\tbilled_quantity NUMERIC(19, 4) NOT NULL, \n\tcustom_fields JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_item_detail PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_item_detail_tenant_id_company_id_line_id UNIQUE (tenant_id, company_id, line_id), \n\tCONSTRAINT fk_voucher_item_detail_1 FOREIGN KEY(tenant_id, company_id, revision_id, line_id) REFERENCES voucher_line (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT ck_voucher_item_detail_quantities CHECK (actual_quantity >= 0 AND billed_quantity >= 0), \n\tCONSTRAINT uq_voucher_item_detail_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_item_detail_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_item_detail")
