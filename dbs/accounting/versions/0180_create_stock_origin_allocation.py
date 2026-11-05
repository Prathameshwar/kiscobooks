"""Native stock authority: stock_origin_allocation; one reviewed reversible CREATE."""
from alembic import op

revision = "0180"
down_revision = "0179"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_origin_allocation (
	origin_id BINARY(16) NOT NULL, 
	movement_id BINARY(16) NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_origin_allocation PRIMARY KEY (id), 
	CONSTRAINT uq_stock_origin_allocation_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_origin_allocation_stock_origin_allocation_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_origin_allocation_origin FOREIGN KEY(tenant_id, company_id, origin_id) REFERENCES stock_receipt_origin (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_origin_allocation_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_origin_allocation UNIQUE (tenant_id, company_id, movement_id, origin_id), 
	CONSTRAINT ck_stock_origin_allocation_stock_origin_allocation_quantity CHECK (quantity <> 0),
	KEY ix_stock_origin_allocation_origin_id (tenant_id, company_id, origin_id),
	KEY ix_stock_origin_allocation_page (tenant_id, company_id, id),
	KEY ix_stock_origin_allocation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_origin_allocation")
