"""Indexed immutable posted lines; one atomic CREATE with scoped references."""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_posted_line (
	cut_id BINARY(16) NOT NULL,
	epoch_id BINARY(16) NOT NULL,
	line_version_id BINARY(16) NOT NULL,
	journal_version_id BINARY(16) NOT NULL,
	line_id BINARY(16) NOT NULL,
	journal_id BINARY(16) NOT NULL,
	account_id BINARY(16) NOT NULL,
	valid_from_sequence BIGINT NOT NULL,
	posting_date DATE NOT NULL,
	line_sequence BIGINT NOT NULL,
	opening_effect BOOL NOT NULL,
	source_bytes INTEGER NOT NULL,
	side VARCHAR(10) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	base_amount NUMERIC(19, 4) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_posted_line PRIMARY KEY (id),
	CONSTRAINT uq_report_posted_line_identity UNIQUE (tenant_id, company_id, epoch_id, line_id),
	CONSTRAINT uq_report_posted_line_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_posted_line_cut_id FOREIGN KEY(tenant_id, company_id, cut_id) REFERENCES report_source_cut (tenant_id, company_id, id),
	CONSTRAINT fk_report_posted_line_epoch_id FOREIGN KEY(tenant_id, company_id, epoch_id) REFERENCES report_source_epoch (tenant_id, company_id, id),
	CONSTRAINT fk_report_posted_line_line_version_id FOREIGN KEY(tenant_id, company_id, line_version_id) REFERENCES report_fact_version (tenant_id, company_id, id),
	CONSTRAINT fk_report_posted_line_journal_version_id FOREIGN KEY(tenant_id, company_id, journal_version_id) REFERENCES report_fact_version (tenant_id, company_id, id),
	INDEX ix_report_posted_line_balance (tenant_id, company_id, epoch_id, account_id, posting_date, journal_id, line_sequence, line_id, valid_from_sequence, side, currency, amount, base_amount),
	INDEX ix_report_posted_line_control (tenant_id, company_id, epoch_id, valid_from_sequence, base_currency, side, base_amount),
	INDEX ix_report_posted_line_date (tenant_id, company_id, epoch_id, posting_date, journal_id, line_sequence, line_id, valid_from_sequence),
	INDEX ix_report_posted_line_page (tenant_id, company_id, id),
	INDEX ix_report_posted_line_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE report_posted_line")
