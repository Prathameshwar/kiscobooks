"""Native stock authority: stock_cost_layer; one reviewed reversible CREATE."""
from alembic import op

revision = "0181"
down_revision = "0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_cost_layer (
	pool_id BINARY(16) NOT NULL, 
	movement_id BINARY(16) NOT NULL, 
	sequence INTEGER NOT NULL, 
	received_on DATE NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	value NUMERIC(19, 4) NOT NULL, 
	remaining_quantity NUMERIC(19, 4) NOT NULL, 
	remaining_value NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_cost_layer PRIMARY KEY (id), 
	CONSTRAINT uq_stock_cost_layer_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_cost_layer_stock_cost_layer_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_cost_layer_pool FOREIGN KEY(tenant_id, company_id, pool_id) REFERENCES stock_cost_pool (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_cost_layer_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_cost_layer_source UNIQUE (tenant_id, company_id, movement_id, sequence), 
	CONSTRAINT ck_stock_cost_layer_stock_cost_layer_balance CHECK (quantity > 0 AND value >= 0 AND remaining_quantity >= 0 AND remaining_quantity <= quantity AND remaining_value >= 0 AND remaining_value <= value AND (remaining_quantity > 0 OR remaining_value = 0)),
	KEY ix_stock_cost_layer_fifo (tenant_id, company_id, pool_id, received_on, id),
	KEY ix_stock_cost_layer_page (tenant_id, company_id, id),
	KEY ix_stock_cost_layer_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_cost_layer")
