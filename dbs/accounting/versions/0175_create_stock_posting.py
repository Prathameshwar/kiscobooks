"""Native stock authority: stock_posting; one reviewed reversible CREATE."""
from alembic import op

revision = "0175"
down_revision = "0174"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_posting (
	intent_id BINARY(16) NOT NULL, 
	execution_id BINARY(16) NOT NULL, 
	operation_id BINARY(16) NOT NULL, 
	voucher_id BINARY(16) NOT NULL, 
	revision_id BINARY(16) NOT NULL, 
	action VARCHAR(24) NOT NULL, 
	stock_date DATE NOT NULL, 
	posting_date DATE NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	journal_id BINARY(16), 
	reverses_id BINARY(16), 
	account_policy_id BINARY(16), 
	content_hash VARCHAR(64) NOT NULL, 
	source_facts JSON NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_posting PRIMARY KEY (id), 
	CONSTRAINT uq_stock_posting_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_posting_stock_posting_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_posting_execution UNIQUE (tenant_id, company_id, execution_id), 
	CONSTRAINT uq_stock_posting_operation UNIQUE (tenant_id, company_id, operation_id), 
	CONSTRAINT uq_stock_posting_reversal UNIQUE (tenant_id, company_id, reverses_id), 
	CONSTRAINT fk_stock_posting_intent FOREIGN KEY(tenant_id, company_id, intent_id) REFERENCES voucher_money_intent (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_posting_journal FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_posting_reversal FOREIGN KEY(tenant_id, company_id, reverses_id) REFERENCES stock_posting (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_posting_policy FOREIGN KEY(tenant_id, company_id, account_policy_id) REFERENCES stock_account_policy (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_posting_stock_posting_action CHECK (action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','CUSTOMER_RETURN','SUPPLIER_RETURN','REVERSAL')),
	KEY ix_stock_posting_account_policy_id (tenant_id, company_id, account_policy_id),
	KEY ix_stock_posting_date (tenant_id, company_id, stock_date, id),
	KEY ix_stock_posting_intent_id (tenant_id, company_id, intent_id),
	KEY ix_stock_posting_journal_id (tenant_id, company_id, journal_id),
	KEY ix_stock_posting_page (tenant_id, company_id, id),
	KEY ix_stock_posting_source (tenant_id, company_id, voucher_id, id),
	KEY ix_stock_posting_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_posting")
