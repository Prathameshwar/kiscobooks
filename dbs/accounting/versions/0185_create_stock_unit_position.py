"""Native stock authority: stock_unit_position; one reviewed reversible CREATE."""
from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_unit_position (
	unit_id BINARY(16) NOT NULL, 
	position_id BINARY(16), 
	last_movement_id BINARY(16) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_unit_position PRIMARY KEY (id), 
	CONSTRAINT uq_stock_unit_position_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_unit_position_stock_unit_position_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_unit_position_unit FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES stock_unit (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_unit_position_position FOREIGN KEY(tenant_id, company_id, position_id) REFERENCES stock_position (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_unit_position_movement FOREIGN KEY(tenant_id, company_id, last_movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_unit_position_unit UNIQUE (tenant_id, company_id, unit_id),
	KEY ix_stock_unit_position_last_movement_id (tenant_id, company_id, last_movement_id),
	KEY ix_stock_unit_position_page (tenant_id, company_id, id),
	KEY ix_stock_unit_position_position (tenant_id, company_id, position_id, id),
	KEY ix_stock_unit_position_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_unit_position")
