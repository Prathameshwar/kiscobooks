"""charge_assessment; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE charge_assessment (
	item_id BINARY(16) NOT NULL,
	policy_id BINARY(16) NOT NULL,
	status VARCHAR(20) NOT NULL,
	coverage_start_date DATE NOT NULL,
	coverage_end_date DATE NOT NULL,
	posting_date DATE NOT NULL,
	due_date DATE NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	cumulative_amount NUMERIC(19, 4) NOT NULL,
	exchange_rate NUMERIC(19, 8) NOT NULL,
	external_reference VARCHAR(120),
	journal_id BINARY(16),
	input_hash VARCHAR(64) NOT NULL,
	snapshot JSON NOT NULL,
	approved_by BINARY(16),
	approved_at DATETIME(6),
	reason VARCHAR(500),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_charge_assessment PRIMARY KEY (id),
	CONSTRAINT uq_charge_assessment_journal UNIQUE (tenant_id, company_id, journal_id),
	CONSTRAINT ck_charge_assessment_charge_assessment_status CHECK (status IN ('DRAFT', 'APPROVED', 'POSTED', 'WAIVED', 'REVERSED', 'REJECTED')),
	CONSTRAINT ck_charge_assessment_charge_assessment_amount CHECK (amount > 0 AND cumulative_amount >= amount AND exchange_rate > 0),
	CONSTRAINT ck_charge_assessment_charge_assessment_dates CHECK (coverage_end_date > coverage_start_date),
	CONSTRAINT uq_charge_assessment_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_charge_assessment_charge_assessment_version CHECK (row_version > 0),
	CONSTRAINT fk_charge_assessment_item_id FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES open_item (tenant_id, company_id, id),
	CONSTRAINT fk_charge_assessment_policy_id FOREIGN KEY(tenant_id, company_id, policy_id) REFERENCES charge_policy (tenant_id, company_id, id),
	CONSTRAINT fk_charge_assessment_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
	INDEX ix_charge_assessment_coverage (tenant_id, company_id, item_id, coverage_end_date, id),
	INDEX ix_charge_assessment_page (tenant_id, company_id, id),
	INDEX ix_charge_assessment_status (tenant_id, company_id, status, posting_date, id),
	INDEX ix_charge_assessment_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE charge_assessment"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
