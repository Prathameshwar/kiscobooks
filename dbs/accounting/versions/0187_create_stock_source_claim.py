"""Native stock authority: stock_source_claim; one reviewed reversible CREATE."""
from alembic import op

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_source_claim (
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
	CONSTRAINT pk_stock_source_claim PRIMARY KEY (id), 
	CONSTRAINT uq_stock_source_claim_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_source_claim_stock_source_claim_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_source_claim_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_source_claim_movement UNIQUE (tenant_id, company_id, movement_id), 
	CONSTRAINT ck_stock_source_claim_stock_source_claim_values CHECK (quantity >= 0 AND value >= 0),
	KEY ix_stock_source_claim_page (tenant_id, company_id, id),
	KEY ix_stock_source_claim_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_source_claim")
