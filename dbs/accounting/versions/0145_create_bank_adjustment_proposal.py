"""Create bank_adjustment_proposal as one DDL statement."""

from alembic import op

revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_adjustment_proposal (
	statement_entry_id BINARY(16) NOT NULL,
	account_id BINARY(16) NOT NULL,
	kind VARCHAR(12) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	status VARCHAR(12) NOT NULL,
	voucher_id BINARY(16),
	reason VARCHAR(500) NOT NULL,
	decision_reason VARCHAR(500),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_adjustment_proposal PRIMARY KEY (id),
	CONSTRAINT uq_bank_proposal_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bank_proposal_entry FOREIGN KEY(tenant_id, company_id, statement_entry_id) REFERENCES bank_statement_entry (tenant_id, company_id, id),
	CONSTRAINT uq_bank_proposal_entry UNIQUE (tenant_id, company_id, statement_entry_id),
	CONSTRAINT ck_bank_adjustment_proposal_bank_proposal_kind CHECK (kind IN ('PAYMENT','RECEIPT','CONTRA','JOURNAL')),
	CONSTRAINT ck_bank_adjustment_proposal_bank_proposal_status CHECK (status IN ('PREPARED','REJECTED','RESOLVED')),
	CONSTRAINT ck_bank_adjustment_proposal_bank_proposal_amount CHECK (amount > 0)
,
	KEY ix_bank_adjustment_proposal_tenant_id (tenant_id),
	KEY ix_bank_proposal_account (tenant_id, company_id, account_id, status, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_adjustment_proposal")
