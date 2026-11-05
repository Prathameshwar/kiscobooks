"""Native stock authority: stock_movement_unit; one reviewed reversible CREATE."""
from alembic import op

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_movement_unit (
	movement_id BINARY(16) NOT NULL, 
	unit_id BINARY(16) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_movement_unit PRIMARY KEY (id), 
	CONSTRAINT uq_stock_movement_unit_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_movement_unit_stock_movement_unit_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_movement_unit_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_movement_unit_unit FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES stock_unit (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_movement_unit UNIQUE (tenant_id, company_id, movement_id, unit_id),
	KEY ix_stock_movement_unit_page (tenant_id, company_id, id),
	KEY ix_stock_movement_unit_tenant_id (tenant_id),
	KEY ix_stock_movement_unit_unit (tenant_id, company_id, unit_id, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_movement_unit")
