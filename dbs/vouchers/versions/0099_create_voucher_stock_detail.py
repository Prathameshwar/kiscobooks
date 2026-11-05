"""Native revision-scoped stock capture; one reversible CREATE."""
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE voucher_stock_detail (
	revision_id BINARY(16) NOT NULL, 
	line_id BINARY(16) NOT NULL, 
	warehouse_id BINARY(16) NOT NULL, 
	bin_id BINARY(16), 
	lot_id BINARY(16), 
	currency VARCHAR(3) NOT NULL, 
	received_value NUMERIC(19, 4), 
	zero_value_reason VARCHAR(500), 
	destination_warehouse_id BINARY(16), 
	destination_bin_id BINARY(16), 
	source_movement_id BINARY(16), 
	opening_journal_line_id BINARY(16), 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_voucher_stock_detail PRIMARY KEY (id), 
	CONSTRAINT uq_voucher_stock_detail_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_voucher_stock_detail_owner UNIQUE (tenant_id, company_id, revision_id, id), 
	CONSTRAINT uq_voucher_stock_detail_line UNIQUE (tenant_id, company_id, revision_id, line_id), 
	CONSTRAINT fk_voucher_stock_detail_context FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_stock_context (tenant_id, company_id, revision_id), 
	CONSTRAINT fk_voucher_stock_detail_line FOREIGN KEY(tenant_id, company_id, revision_id, line_id) REFERENCES voucher_line (tenant_id, company_id, revision_id, id), 
	CONSTRAINT ck_voucher_stock_detail_voucher_stock_detail_version CHECK (row_version > 0), 
	CONSTRAINT ck_voucher_stock_detail_voucher_stock_detail_value CHECK ((received_value IS NULL AND zero_value_reason IS NULL) OR (received_value = 0 AND zero_value_reason IS NOT NULL) OR (received_value > 0 AND zero_value_reason IS NULL)),
	KEY ix_voucher_stock_detail_source (tenant_id, company_id, source_movement_id, id),
	KEY ix_voucher_stock_detail_tenant_id (tenant_id),
	KEY ix_voucher_stock_detail_warehouse (tenant_id, company_id, warehouse_id, id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    op.execute("DROP TABLE voucher_stock_detail")
