"""Prepared tracking identity: stock_unit; one reversible DDL."""
from alembic import op

revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_unit (
	item_id BINARY(16) NOT NULL, 
	lot_id BINARY(16), 
	status VARCHAR(16) NOT NULL, 
	is_held BOOL NOT NULL, 
	source_facts JSON NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_unit PRIMARY KEY (id), 
	CONSTRAINT uq_stock_unit_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_unit_stock_unit_version CHECK (row_version > 0), 
	CONSTRAINT ck_stock_unit_stock_unit_status CHECK (status IN ('ACTIVE','RETIRED')), 
	CONSTRAINT fk_stock_unit_lot FOREIGN KEY(tenant_id, company_id, lot_id) REFERENCES stock_lot (tenant_id, company_id, id),
	KEY ix_stock_unit_item (tenant_id, company_id, item_id, id),
	KEY ix_stock_unit_lot (tenant_id, company_id, lot_id, id),
	KEY ix_stock_unit_page (tenant_id, company_id, id),
	KEY ix_stock_unit_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_unit")
