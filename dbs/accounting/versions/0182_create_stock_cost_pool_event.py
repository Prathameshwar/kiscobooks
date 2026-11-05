"""Native stock authority: stock_cost_pool_event; one reviewed reversible CREATE."""
from alembic import op

revision = "0182"
down_revision = "0181"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_cost_pool_event (
	pool_id BINARY(16) NOT NULL, 
	movement_id BINARY(16) NOT NULL, 
	method VARCHAR(20) NOT NULL, 
	before_quantity NUMERIC(19, 4) NOT NULL, 
	after_quantity NUMERIC(19, 4) NOT NULL, 
	before_value NUMERIC(19, 4) NOT NULL, 
	after_value NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_cost_pool_event PRIMARY KEY (id), 
	CONSTRAINT uq_stock_cost_pool_event_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_cost_pool_event_stock_cost_pool_event_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_pool_event_pool FOREIGN KEY(tenant_id, company_id, pool_id) REFERENCES stock_cost_pool (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_pool_event_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_pool_event_movement UNIQUE (tenant_id, company_id, movement_id), 
	CONSTRAINT ck_stock_cost_pool_event_stock_pool_event_values CHECK (before_quantity >= 0 AND after_quantity >= 0 AND before_value >= 0 AND after_value >= 0), 
	CONSTRAINT ck_stock_cost_pool_event_stock_pool_event_method CHECK (method IN ('FIFO','MOVING_AVERAGE')),
	KEY ix_stock_cost_pool_event_page (tenant_id, company_id, id),
	KEY ix_stock_cost_pool_event_tenant_id (tenant_id),
	KEY ix_stock_pool_event_pool (tenant_id, company_id, pool_id, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_cost_pool_event")
