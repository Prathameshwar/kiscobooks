"""open_item; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE open_item (
	journal_line_id BINARY(16) NOT NULL,
	sequence INTEGER NOT NULL,
	account_id BINARY(16) NOT NULL,
	party_id BINARY(16) NOT NULL,
	`role` VARCHAR(20) NOT NULL,
	direction VARCHAR(10) NOT NULL,
	reference VARCHAR(120) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	base_amount NUMERIC(19, 4) NOT NULL,
	document_date DATE NOT NULL,
	posting_date DATE NOT NULL,
	due_date DATE NOT NULL,
	terms JSON NOT NULL,
	reversal_journal_id BINARY(16),
	reversal_date DATE,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_open_item PRIMARY KEY (id),
	CONSTRAINT uq_open_item_line_sequence UNIQUE (tenant_id, company_id, journal_line_id, sequence),
	CONSTRAINT ck_open_item_open_item_direction CHECK (direction IN ('DEBT', 'CREDIT')),
	CONSTRAINT ck_open_item_open_item_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')),
	CONSTRAINT ck_open_item_open_item_amount CHECK (amount > 0 AND base_amount > 0 AND sequence > 0),
	CONSTRAINT ck_open_item_open_item_reversal CHECK ((reversal_journal_id IS NULL AND reversal_date IS NULL) OR (reversal_journal_id IS NOT NULL AND reversal_date IS NOT NULL)),
	CONSTRAINT uq_open_item_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_open_item_open_item_version CHECK (row_version > 0),
	CONSTRAINT fk_open_item_journal_line_id FOREIGN KEY(tenant_id, company_id, journal_line_id) REFERENCES journal_line (tenant_id, company_id, id),
	CONSTRAINT fk_open_item_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_open_item_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	CONSTRAINT fk_open_item_reversal_journal_id FOREIGN KEY(tenant_id, company_id, reversal_journal_id) REFERENCES journal (tenant_id, company_id, id),
	INDEX ix_open_item_account (tenant_id, company_id, account_id, posting_date, id),
	INDEX ix_open_item_due (tenant_id, company_id, due_date, id),
	INDEX ix_open_item_exposure (tenant_id, company_id, party_id, `role`, currency, posting_date, id),
	INDEX ix_open_item_page (tenant_id, company_id, id),
	INDEX ix_open_item_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE open_item"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
