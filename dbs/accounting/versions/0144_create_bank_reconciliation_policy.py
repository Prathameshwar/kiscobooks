"""Create bank_reconciliation_policy as one DDL statement."""

from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_reconciliation_policy (
	account_id BINARY(16) NOT NULL,
	revision INTEGER NOT NULL,
	mode VARCHAR(20) NOT NULL,
	match_window_days INTEGER NOT NULL,
	require_separate_reviewer BOOL NOT NULL DEFAULT '0',
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_reconciliation_policy PRIMARY KEY (id),
	CONSTRAINT uq_bank_policy_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bank_policy_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT uq_bank_policy_revision UNIQUE (tenant_id, company_id, account_id, revision),
	CONSTRAINT ck_bank_reconciliation_policy_bank_policy_mode CHECK (mode IN ('MANUAL_ONLY','SUGGEST_AND_REVIEW')),
	CONSTRAINT ck_bank_reconciliation_policy_bank_policy_window CHECK (match_window_days BETWEEN 0 AND 90)
,
	KEY ix_bank_policy_account (tenant_id, company_id, account_id, revision),
	KEY ix_bank_reconciliation_policy_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_reconciliation_policy")
