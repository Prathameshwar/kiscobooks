"""Native revision-scoped stock capture; one reversible CREATE."""
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE voucher_stock_unit (
	revision_id BINARY(16) NOT NULL, 
	stock_detail_id BINARY(16) NOT NULL, 
	unit_id BINARY(16) NOT NULL, 
	sequence INTEGER NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_voucher_stock_unit PRIMARY KEY (id), 
	CONSTRAINT uq_voucher_stock_unit_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_voucher_stock_unit_once UNIQUE (tenant_id, company_id, revision_id, unit_id), 
	CONSTRAINT uq_voucher_stock_unit_sequence UNIQUE (tenant_id, company_id, stock_detail_id, sequence), 
	CONSTRAINT fk_voucher_stock_unit_detail FOREIGN KEY(tenant_id, company_id, revision_id, stock_detail_id) REFERENCES voucher_stock_detail (tenant_id, company_id, revision_id, id), 
	CONSTRAINT ck_voucher_stock_unit_voucher_stock_unit_sequence CHECK (sequence BETWEEN 1 AND 200 AND row_version > 0),
	KEY ix_voucher_stock_unit_detail (tenant_id, company_id, revision_id, stock_detail_id),
	KEY ix_voucher_stock_unit_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    op.execute("DROP TABLE voucher_stock_unit")
