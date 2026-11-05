"""Guarded source/cohort claim projection; one reversible CREATE."""
from alembic import op

revision = "0196"
down_revision = "0195"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE stock_origin_claim (
	source_movement_id BINARY(16) NOT NULL, 
	origin_id BINARY(16) NOT NULL, 
	claim_type VARCHAR(16) NOT NULL, 
	quantity NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_origin_claim PRIMARY KEY (id), 
	CONSTRAINT uq_stock_origin_claim_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_origin_claim_stock_origin_claim_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_origin_claim_movement FOREIGN KEY(tenant_id, company_id, source_movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_origin_claim_origin FOREIGN KEY(tenant_id, company_id, origin_id) REFERENCES stock_receipt_origin (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_origin_claim_identity UNIQUE (tenant_id, company_id, source_movement_id, origin_id, claim_type), 
	CONSTRAINT ck_stock_origin_claim_stock_origin_claim_quantity CHECK (quantity >= 0), 
	CONSTRAINT ck_stock_origin_claim_stock_origin_claim_type CHECK (claim_type IN ('RETURN','TRANSFER','INVOICE','REVERSAL')),
	KEY ix_stock_origin_claim_origin_id (tenant_id, company_id, origin_id),
	KEY ix_stock_origin_claim_page (tenant_id, company_id, id),
	KEY ix_stock_origin_claim_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    op.execute("DROP TABLE stock_origin_claim")
