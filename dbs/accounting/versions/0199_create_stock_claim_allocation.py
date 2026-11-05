"""Immutable source claim allocation evidence; one reversible CREATE."""
from alembic import op

revision = "0199"
down_revision = "0198"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE stock_claim_allocation (
	source_movement_id BINARY(16) NOT NULL, 
	movement_id BINARY(16) NOT NULL, 
	claim_type VARCHAR(16) NOT NULL, 
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
	CONSTRAINT pk_stock_claim_allocation PRIMARY KEY (id), 
	CONSTRAINT uq_stock_claim_allocation_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_claim_allocation_stock_claim_allocation_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_claim_allocation_source FOREIGN KEY(tenant_id, company_id, source_movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_claim_allocation_movement FOREIGN KEY(tenant_id, company_id, movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_claim_allocation_move UNIQUE (tenant_id, company_id, movement_id, claim_type), 
	CONSTRAINT ck_stock_claim_allocation_stock_claim_allocation_values CHECK (quantity > 0 AND value >= 0), 
	CONSTRAINT ck_stock_claim_allocation_stock_claim_allocation_type CHECK (claim_type IN ('RETURN','TRANSFER','INVOICE','REVERSAL')),
	KEY ix_stock_claim_allocation_page (tenant_id, company_id, id),
	KEY ix_stock_claim_allocation_source (tenant_id, company_id, source_movement_id, id),
	KEY ix_stock_claim_allocation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    op.execute("DROP TABLE stock_claim_allocation")
