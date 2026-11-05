"""Create bank_statement_entry as one DDL statement."""

from alembic import op

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_statement_entry (
	import_id BINARY(16) NOT NULL,
	account_id BINARY(16) NOT NULL,
	line_number INTEGER NOT NULL,
	transaction_date DATE NOT NULL,
	side VARCHAR(10) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	reference VARCHAR(500) NOT NULL,
	description VARCHAR(500) NOT NULL,
	transaction_id VARCHAR(500),
	row_sha256 VARCHAR(64) NOT NULL,
	review_status VARCHAR(12) NOT NULL,
	running_balance NUMERIC(19, 4),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_statement_entry PRIMARY KEY (id),
	CONSTRAINT uq_bs_entry_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bs_entry_import FOREIGN KEY(tenant_id, company_id, import_id) REFERENCES bank_statement_import (tenant_id, company_id, id),
	CONSTRAINT uq_bs_entry_line UNIQUE (tenant_id, company_id, import_id, line_number),
	CONSTRAINT ck_bank_statement_entry_statement_entry_side CHECK (side IN ('DEBIT','CREDIT')),
	CONSTRAINT ck_bank_statement_entry_statement_entry_amount CHECK (amount > 0),
	CONSTRAINT ck_bank_statement_entry_statement_entry_review CHECK (review_status IN ('NEW','EXISTING','AMBIGUOUS','ACCEPTED'))
,
	KEY ix_bank_statement_entry_tenant_id (tenant_id),
	KEY ix_statement_entry_account (tenant_id, company_id, account_id, transaction_date, id),
	KEY ix_statement_entry_external (tenant_id, company_id, account_id, transaction_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_statement_entry")
