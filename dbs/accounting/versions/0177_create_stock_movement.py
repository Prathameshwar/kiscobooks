"""Native stock authority: stock_movement; one reviewed reversible CREATE."""
from alembic import op

revision = "0177"
down_revision = "0176"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_movement (
	posting_id BINARY(16) NOT NULL, 
	position_id BINARY(16) NOT NULL, 
	pool_id BINARY(16) NOT NULL, 
	line_id BINARY(16) NOT NULL, 
	leg VARCHAR(3) NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	source_movement_id BINARY(16), 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_movement PRIMARY KEY (id), 
	CONSTRAINT uq_stock_movement_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_movement_stock_movement_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_movement_posting FOREIGN KEY(tenant_id, company_id, posting_id) REFERENCES stock_posting (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_movement_position FOREIGN KEY(tenant_id, company_id, position_id) REFERENCES stock_position (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_movement_pool FOREIGN KEY(tenant_id, company_id, pool_id) REFERENCES stock_cost_pool (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_movement_source FOREIGN KEY(tenant_id, company_id, source_movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_movement_source_leg UNIQUE (tenant_id, company_id, posting_id, line_id, leg), 
	CONSTRAINT ck_stock_movement_stock_movement_quantity CHECK (quantity <> 0 AND leg IN ('IN','OUT')), 
	CONSTRAINT ck_stock_movement_stock_movement_direction CHECK ((leg = 'IN' AND quantity > 0) OR (leg = 'OUT' AND quantity < 0)),
	KEY ix_stock_movement_page (tenant_id, company_id, id),
	KEY ix_stock_movement_pool_id (tenant_id, company_id, pool_id),
	KEY ix_stock_movement_position (tenant_id, company_id, position_id, id),
	KEY ix_stock_movement_source (tenant_id, company_id, source_movement_id, id),
	KEY ix_stock_movement_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_movement")
