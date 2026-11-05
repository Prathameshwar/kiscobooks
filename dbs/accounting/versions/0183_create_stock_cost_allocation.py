"""Native stock authority: stock_cost_allocation; one reviewed reversible CREATE."""
from alembic import op

revision = "0183"
down_revision = "0182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_cost_allocation (
	pool_id BINARY(16) NOT NULL, 
	layer_id BINARY(16), 
	layer_key BINARY(16) NOT NULL, 
	movement_id BINARY(16) NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	value NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_cost_allocation PRIMARY KEY (id), 
	CONSTRAINT uq_stock_cost_allocation_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_cost_allocation_stock_cost_allocation_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_cost_allocation_pool FOREIGN KEY(tenant_id, company_id, pool_id) REFERENCES stock_cost_pool (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_cost_allocation_layer FOREIGN KEY(tenant_id, company_id, layer_id) REFERENCES stock_cost_layer (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_cost_allocation_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_cost_allocation_layer UNIQUE (tenant_id, company_id, movement_id, layer_key), 
	CONSTRAINT ck_stock_cost_allocation_stock_cost_allocation_key CHECK ((layer_id IS NULL AND layer_key = X'00000000000000000000000000000000') OR (layer_id IS NOT NULL AND layer_key = layer_id)), 
	CONSTRAINT ck_stock_cost_allocation_stock_cost_allocation_values CHECK (quantity > 0 AND value >= 0),
	KEY ix_stock_cost_allocation_layer_id (tenant_id, company_id, layer_id),
	KEY ix_stock_cost_allocation_movement (tenant_id, company_id, movement_id, id),
	KEY ix_stock_cost_allocation_page (tenant_id, company_id, id),
	KEY ix_stock_cost_allocation_pool_id (tenant_id, company_id, pool_id),
	KEY ix_stock_cost_allocation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_cost_allocation")
