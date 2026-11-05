"""Create bank_reconciliation_session as one DDL statement."""

from alembic import op

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_reconciliation_session (
	account_id BINARY(16) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	period_from DATE NOT NULL,
	period_to DATE NOT NULL,
	generation INTEGER NOT NULL,
	opening_balance NUMERIC(19, 4) NOT NULL,
	closing_balance NUMERIC(19, 4) NOT NULL,
	status VARCHAR(12) NOT NULL,
	snapshot JSON NOT NULL,
	reason VARCHAR(500) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_reconciliation_session PRIMARY KEY (id),
	CONSTRAINT uq_bank_session_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bank_session_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT uq_bank_session_period UNIQUE (tenant_id, company_id, account_id, period_from, period_to, generation),
	CONSTRAINT ck_bank_reconciliation_session_bank_session_status CHECK (status IN ('DRAFT','FINALIZED','AMENDED'))
,
	KEY ix_bank_reconciliation_session_tenant_id (tenant_id),
	KEY ix_bank_session_account (tenant_id, company_id, account_id, period_to, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_reconciliation_session")
