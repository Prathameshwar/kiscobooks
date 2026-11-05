"""journal_line; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE journal_line (
	journal_id BINARY(16) NOT NULL,
	component VARCHAR(20) NOT NULL DEFAULT 'PRINCIPAL',
	sequence INTEGER NOT NULL,
	account_id BINARY(16) NOT NULL,
	side VARCHAR(10) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	exchange_rate NUMERIC(19, 8) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	base_amount NUMERIC(19, 4) NOT NULL,
	party_id BINARY(16),
	`role` VARCHAR(20),
	description VARCHAR(500),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_journal_line PRIMARY KEY (id),
	CONSTRAINT uq_journal_line_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_journal_line_sequence UNIQUE (tenant_id, company_id, journal_id, sequence),
	CONSTRAINT fk_journal_line_journal FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_journal_line_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_journal_line_party FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	CONSTRAINT ck_journal_line_journal_line_version CHECK (row_version > 0),
	CONSTRAINT ck_journal_line_journal_line_sequence CHECK (sequence BETWEEN 1 AND 200),
	CONSTRAINT ck_journal_line_journal_line_side CHECK (side IN ('DEBIT', 'CREDIT')),
	CONSTRAINT ck_journal_line_journal_line_amount CHECK (base_amount > 0 AND exchange_rate > 0 AND ((component = 'PRINCIPAL' AND amount > 0) OR (component = 'FX' AND amount = 0 AND party_id IS NOT NULL))),
	CONSTRAINT ck_journal_line_journal_line_party CHECK ((party_id IS NULL AND role IS NULL) OR (party_id IS NOT NULL AND role IN ('CUSTOMER', 'SUPPLIER'))),
	INDEX ix_journal_line_account (tenant_id, company_id, account_id, journal_id),
	INDEX ix_journal_line_party (tenant_id, company_id, party_id, `role`, journal_id),
	INDEX ix_journal_line_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE journal_line"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
