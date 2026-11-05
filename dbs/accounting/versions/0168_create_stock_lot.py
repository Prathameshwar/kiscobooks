"""Prepared tracking identity: stock_lot; one reversible DDL."""
from alembic import op

revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_lot (
	item_id BINARY(16) NOT NULL, 
	code VARCHAR(100) NOT NULL, 
	normalized_code VARCHAR(100) COLLATE utf8mb4_bin NOT NULL, 
	namespace_key VARCHAR(40) NOT NULL, 
	source_party_id BINARY(16), 
	manufactured_on DATE, 
	expires_on DATE, 
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
	CONSTRAINT pk_stock_lot PRIMARY KEY (id), 
	CONSTRAINT uq_stock_lot_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_lot_stock_lot_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_lot_identity UNIQUE (tenant_id, company_id, item_id, namespace_key, normalized_code), 
	CONSTRAINT ck_stock_lot_stock_lot_status CHECK (status IN ('ACTIVE','RETIRED')), 
	CONSTRAINT ck_stock_lot_stock_lot_dates CHECK (expires_on IS NULL OR manufactured_on IS NULL OR expires_on >= manufactured_on), 
	CONSTRAINT fk_stock_lot_source_party FOREIGN KEY(tenant_id, company_id, source_party_id) REFERENCES party (tenant_id, company_id, id),
	KEY ix_stock_lot_code (tenant_id, company_id, normalized_code, id),
	KEY ix_stock_lot_expiry (tenant_id, company_id, expires_on, id),
	KEY ix_stock_lot_item (tenant_id, company_id, item_id, id),
	KEY ix_stock_lot_source_party (tenant_id, company_id, source_party_id, id),
	KEY ix_stock_lot_page (tenant_id, company_id, id),
	KEY ix_stock_lot_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_lot")
