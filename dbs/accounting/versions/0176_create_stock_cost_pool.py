"""Native stock authority: stock_cost_pool; one reviewed reversible CREATE."""
from alembic import op

revision = "0176"
down_revision = "0175"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_cost_pool (
	item_id BINARY(16) NOT NULL, 
	warehouse_id BINARY(16) NOT NULL, 
	method VARCHAR(20) NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	value NUMERIC(19, 4) NOT NULL, 
	last_stock_date DATE, 
	last_posting_id BINARY(16), 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_cost_pool PRIMARY KEY (id), 
	CONSTRAINT uq_stock_cost_pool_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_cost_pool_stock_cost_pool_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_cost_pool_identity UNIQUE (tenant_id, company_id, item_id, warehouse_id), 
	CONSTRAINT fk_stock_cost_pool_posting FOREIGN KEY(tenant_id, company_id, last_posting_id) REFERENCES stock_posting (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_cost_pool_stock_cost_pool_method CHECK (method IN ('FIFO','MOVING_AVERAGE')), 
	CONSTRAINT ck_stock_cost_pool_stock_cost_pool_balance CHECK (quantity >= 0 AND value >= 0 AND (quantity > 0 OR value = 0)),
	KEY ix_stock_cost_pool_last_posting_id (tenant_id, company_id, last_posting_id),
	KEY ix_stock_cost_pool_page (tenant_id, company_id, id),
	KEY ix_stock_cost_pool_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_cost_pool")
