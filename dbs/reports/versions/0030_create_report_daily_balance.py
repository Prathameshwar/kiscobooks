"""Exact immutable per-cut daily deltas; one atomic CREATE with scoped references."""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_daily_balance (
	cut_id BINARY(16) NOT NULL,
	epoch_id BINARY(16) NOT NULL,
	valid_from_sequence BIGINT NOT NULL,
	account_id BINARY(16) NOT NULL,
	posting_date DATE NOT NULL,
	currency VARCHAR(3) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	side VARCHAR(10) NOT NULL,
	opening_effect BOOL NOT NULL,
	line_count BIGINT NOT NULL,
	amount NUMERIC(38, 4) NOT NULL,
	base_amount NUMERIC(38, 4) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_daily_balance PRIMARY KEY (id),
	CONSTRAINT uq_report_daily_balance_grain UNIQUE (tenant_id, company_id, epoch_id, valid_from_sequence, account_id, posting_date, currency, base_currency, side, opening_effect),
	CONSTRAINT ck_report_daily_balance_ck_report_daily_balance_values CHECK (line_count > 0 AND amount >= 0 AND base_amount >= 0 AND valid_from_sequence >= 0),
	CONSTRAINT ck_report_daily_balance_ck_report_daily_balance_side CHECK (side IN ('DEBIT', 'CREDIT')),
	CONSTRAINT uq_report_daily_balance_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_daily_balance_cut_id FOREIGN KEY(tenant_id, company_id, cut_id) REFERENCES report_source_cut (tenant_id, company_id, id),
	CONSTRAINT fk_report_daily_balance_epoch_id FOREIGN KEY(tenant_id, company_id, epoch_id) REFERENCES report_source_epoch (tenant_id, company_id, id),
	INDEX ix_report_daily_balance_account (tenant_id, company_id, epoch_id, account_id, posting_date, valid_from_sequence),
	INDEX ix_report_daily_balance_cut (tenant_id, company_id, epoch_id, valid_from_sequence, base_currency, side),
	INDEX ix_report_daily_balance_page (tenant_id, company_id, id),
	INDEX ix_report_daily_balance_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE report_daily_balance")
