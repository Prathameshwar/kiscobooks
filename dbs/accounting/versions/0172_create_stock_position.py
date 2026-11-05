"""Native stock authority: stock_position; one reviewed reversible CREATE."""
from alembic import op

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_position (
	item_id BINARY(16) NOT NULL, 
	warehouse_id BINARY(16) NOT NULL, 
	bin_id BINARY(16), 
	bin_key BINARY(16) NOT NULL, 
	lot_id BINARY(16), 
	lot_key BINARY(16) NOT NULL, 
	owner_kind VARCHAR(20) NOT NULL, 
	custody_kind VARCHAR(20) NOT NULL, 
	disposition VARCHAR(20) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_position PRIMARY KEY (id), 
	CONSTRAINT uq_stock_position_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_position_stock_position_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_position_identity UNIQUE (tenant_id, company_id, item_id, warehouse_id, bin_key, lot_key, disposition), 
	CONSTRAINT fk_stock_position_lot FOREIGN KEY(tenant_id, company_id, lot_id) REFERENCES stock_lot (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_position_stock_position_lot_key CHECK ((lot_id IS NULL AND lot_key = X'00000000000000000000000000000000') OR (lot_id IS NOT NULL AND lot_key = lot_id)), 
	CONSTRAINT ck_stock_position_stock_position_bin_key CHECK ((bin_id IS NULL AND bin_key = X'00000000000000000000000000000000') OR (bin_id IS NOT NULL AND bin_key = bin_id)), 
	CONSTRAINT ck_stock_position_stock_position_supported_scope CHECK (owner_kind = 'COMPANY' AND custody_kind = 'WAREHOUSE' AND disposition = 'USABLE'),
	KEY ix_stock_position_item (tenant_id, company_id, item_id, warehouse_id, id),
	KEY ix_stock_position_lot_id (tenant_id, company_id, lot_id),
	KEY ix_stock_position_page (tenant_id, company_id, id),
	KEY ix_stock_position_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_position")
