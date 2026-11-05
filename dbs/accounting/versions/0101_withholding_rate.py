"""withholding_rate; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE withholding_rate (
	section_id BINARY(16) NOT NULL,
	deductee_type VARCHAR(40) NOT NULL,
	rate_percent NUMERIC(19, 4) NOT NULL,
	no_pan_rate_percent NUMERIC(19, 4) NOT NULL,
	single_transaction_threshold NUMERIC(19, 4),
	aggregate_annual_threshold NUMERIC(19, 4),
	threshold_currency VARCHAR(3) NOT NULL,
	threshold_basis VARCHAR(20) NOT NULL,
	source_reference VARCHAR(500) NOT NULL,
	source_url VARCHAR(1000) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	supersedes_id BINARY(16),
	valid_from DATE NOT NULL,
	valid_to DATE,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_withholding_rate PRIMARY KEY (id),
	CONSTRAINT uq_withholding_rate_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_withholding_rate_withholding_rate_version CHECK (row_version > 0),
	CONSTRAINT fk_withholding_rate_section_id FOREIGN KEY(tenant_id, company_id, section_id) REFERENCES withholding_section (tenant_id, company_id, id),
	CONSTRAINT fk_withholding_rate_supersedes_id FOREIGN KEY(tenant_id, company_id, supersedes_id) REFERENCES withholding_rate (tenant_id, company_id, id),
	CONSTRAINT ck_withholding_rate_withholding_rate_deductee_type CHECK (deductee_type IN ('INDIVIDUAL', 'HUF', 'COMPANY', 'FIRM', 'AOP_BOI', 'LOCAL_AUTHORITY', 'ARTIFICIAL_JURIDICAL_PERSON', 'GOVERNMENT', 'COOPERATIVE', 'TRUST', 'NON_RESIDENT_COMPANY', 'NON_RESIDENT_OTHER', 'OTHER')),
	CONSTRAINT ck_withholding_rate_withholding_rate_percent CHECK (rate_percent >= 0 AND rate_percent <= 100 AND no_pan_rate_percent >= rate_percent AND no_pan_rate_percent <= 100),
	CONSTRAINT ck_withholding_rate_withholding_rate_threshold CHECK ((single_transaction_threshold IS NULL OR single_transaction_threshold > 0) AND (aggregate_annual_threshold IS NULL OR aggregate_annual_threshold > 0)),
	CONSTRAINT ck_withholding_rate_withholding_rate_basis CHECK (threshold_basis IN ('TRANSACTION', 'AGGREGATE', 'EXCESS')),
	CONSTRAINT ck_withholding_rate_withholding_rate_evidence CHECK (LENGTH(source_sha256) = 64),
	CONSTRAINT ck_withholding_rate_withholding_rate_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	INDEX ix_withholding_rate_asof (tenant_id, company_id, valid_from, id),
	INDEX ix_withholding_rate_page (tenant_id, company_id, id),
	INDEX ix_withholding_rate_ref0 (tenant_id, company_id, supersedes_id),
	INDEX ix_withholding_rate_tenant_id (tenant_id),
	INDEX ix_withholding_rate_term (tenant_id, company_id, section_id, deductee_type, valid_from)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE withholding_rate"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
