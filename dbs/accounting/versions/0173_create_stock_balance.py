"""Native stock authority: stock_balance; one reviewed reversible CREATE."""
from alembic import op

revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_balance (
	position_id BINARY(16) NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_balance PRIMARY KEY (id), 
	CONSTRAINT uq_stock_balance_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_balance_stock_balance_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_balance_position UNIQUE (tenant_id, company_id, position_id), 
	CONSTRAINT fk_stock_balance_position FOREIGN KEY(tenant_id, company_id, position_id) REFERENCES stock_position (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_balance_stock_balance_nonnegative CHECK (quantity >= 0),
	KEY ix_stock_balance_page (tenant_id, company_id, id),
	KEY ix_stock_balance_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_balance")
