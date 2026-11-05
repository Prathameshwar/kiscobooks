"""Native stock authority: stock_value_entry; one reviewed reversible CREATE."""
from alembic import op

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_value_entry (
	movement_id BINARY(16) NOT NULL, 
	pool_id BINARY(16) NOT NULL, 
	amount NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_value_entry PRIMARY KEY (id), 
	CONSTRAINT uq_stock_value_entry_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_value_entry_stock_value_entry_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_value_entry_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_value_entry_pool FOREIGN KEY(tenant_id, company_id, pool_id) REFERENCES stock_cost_pool (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_value_entry_movement UNIQUE (tenant_id, company_id, movement_id),
	KEY ix_stock_value_entry_page (tenant_id, company_id, id),
	KEY ix_stock_value_entry_pool (tenant_id, company_id, pool_id, id),
	KEY ix_stock_value_entry_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_value_entry")
