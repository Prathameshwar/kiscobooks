"""Native stock authority: stock_opening_bridge; one reviewed reversible CREATE."""
from alembic import op

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_opening_bridge (
	value_entry_id BINARY(16) NOT NULL, 
	journal_line_id BINARY(16) NOT NULL, 
	amount NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_opening_bridge PRIMARY KEY (id), 
	CONSTRAINT uq_stock_opening_bridge_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_opening_bridge_stock_opening_bridge_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_opening_bridge_value FOREIGN KEY(tenant_id, company_id, value_entry_id) REFERENCES stock_value_entry (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_opening_bridge_journal_line FOREIGN KEY(tenant_id, company_id, journal_line_id) REFERENCES journal_line (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_opening_bridge_value UNIQUE (tenant_id, company_id, value_entry_id), 
	CONSTRAINT ck_stock_opening_bridge_stock_opening_bridge_amount CHECK (amount > 0),
	KEY ix_stock_opening_bridge_line (tenant_id, company_id, journal_line_id, id),
	KEY ix_stock_opening_bridge_page (tenant_id, company_id, id),
	KEY ix_stock_opening_bridge_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_opening_bridge")
