"""journal; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE journal (
	kind VARCHAR(30) NOT NULL,
	status VARCHAR(20) NOT NULL,
	document_date DATE NOT NULL,
	posting_date DATE NOT NULL,
	description VARCHAR(1000) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	total_debit NUMERIC(19, 4) NOT NULL,
	total_credit NUMERIC(19, 4) NOT NULL,
	source_system VARCHAR(40) NOT NULL,
	source_type VARCHAR(40) NOT NULL,
	source_id VARCHAR(120) NOT NULL,
	source_hash VARCHAR(64) NOT NULL,
	number VARCHAR(100),
	fiscal_period_id BINARY(16),
	authorization_journal_id BINARY(16),
	reversal_of_id BINARY(16),
	live_reversal_id BINARY(16) GENERATED ALWAYS AS (CASE WHEN status = 'VOID' THEN NULL ELSE reversal_of_id END) STORED,
	configuration_hash VARCHAR(64) NOT NULL,
	features JSON NOT NULL,
	prepared_at DATETIME(6),
	prepared_by BINARY(16),
	prepared_version INTEGER,
	reservation_id BINARY(16),
	posted_at DATETIME(6),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_journal PRIMARY KEY (id),
	CONSTRAINT uq_journal_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_journal_number UNIQUE (tenant_id, company_id, number),
	CONSTRAINT uq_journal_source UNIQUE (tenant_id, company_id, source_system, source_type, source_id),
	CONSTRAINT uq_journal_reversal UNIQUE (tenant_id, company_id, live_reversal_id),
	CONSTRAINT fk_journal_period FOREIGN KEY(tenant_id, company_id, fiscal_period_id) REFERENCES fiscal_period (tenant_id, company_id, id),
	CONSTRAINT fk_journal_reversal FOREIGN KEY(tenant_id, company_id, reversal_of_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_journal_authorization FOREIGN KEY(tenant_id, company_id, authorization_journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT ck_journal_journal_version CHECK (row_version > 0),
	CONSTRAINT ck_journal_journal_status CHECK (status IN ('DRAFT', 'PREPARED', 'POSTED', 'VOID')),
	CONSTRAINT ck_journal_journal_kind CHECK (kind IN ('MANUAL', 'OPENING', 'INVOICE', 'BILL', 'RECEIPT', 'PAYMENT', 'CREDIT_NOTE', 'CHARGE', 'REVERSAL', 'REALIZED_FX')),
	CONSTRAINT ck_journal_journal_balanced CHECK (total_debit = total_credit AND total_debit > 0),
	CONSTRAINT ck_journal_journal_posted CHECK ((status <> 'POSTED') OR (number IS NOT NULL AND fiscal_period_id IS NOT NULL AND posted_at IS NOT NULL AND reservation_id IS NOT NULL)),
	CONSTRAINT ck_journal_journal_prepared CHECK ((status NOT IN ('PREPARED', 'POSTED')) OR (prepared_by IS NOT NULL AND prepared_at IS NOT NULL AND prepared_version IS NOT NULL)),
	INDEX ix_journal_date (tenant_id, company_id, posting_date, id),
	INDEX ix_journal_page (tenant_id, company_id, id),
	INDEX ix_journal_period (tenant_id, company_id, fiscal_period_id, id),
	INDEX ix_journal_status_date (tenant_id, company_id, status, posting_date, id),
	INDEX ix_journal_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE journal"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
