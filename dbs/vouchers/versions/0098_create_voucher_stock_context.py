"""Native revision-scoped stock capture; one reversible CREATE."""
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE voucher_stock_context (
	revision_id BINARY(16) NOT NULL, 
	schema_version INTEGER NOT NULL, 
	action VARCHAR(24) NOT NULL, 
	opening_mode VARCHAR(16), 
	reason VARCHAR(500) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_voucher_stock_context PRIMARY KEY (id), 
	CONSTRAINT uq_voucher_stock_context_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_voucher_stock_context_revision UNIQUE (tenant_id, company_id, revision_id), 
	CONSTRAINT fk_voucher_stock_context_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_voucher_stock_context_voucher_stock_context_version CHECK (schema_version = 1 AND row_version > 0), 
	CONSTRAINT ck_voucher_stock_context_voucher_stock_context_action CHECK (action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH','TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN')), 
	CONSTRAINT ck_voucher_stock_context_voucher_stock_context_opening CHECK ((action = 'OPENING' AND opening_mode IS NOT NULL AND opening_mode IN ('COMBINED','LINKED_GL')) OR (action <> 'OPENING' AND opening_mode IS NULL)),
	KEY ix_voucher_stock_context_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    op.execute("DROP TABLE voucher_stock_context")
