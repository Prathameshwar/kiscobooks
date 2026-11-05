"""fiscal_period; indexes and foreign keys created by one atomic DDL."""
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE fiscal_period (
	fiscal_year_id BINARY(16) NOT NULL,
	sequence INTEGER NOT NULL,
	code VARCHAR(40) NOT NULL,
	start_date DATE NOT NULL,
	end_date DATE NOT NULL,
	status VARCHAR(20) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_fiscal_period PRIMARY KEY (id),
	CONSTRAINT uq_fiscal_period_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_fiscal_period_sequence UNIQUE (tenant_id, company_id, fiscal_year_id, sequence),
	CONSTRAINT fk_fiscal_period_year FOREIGN KEY(tenant_id, company_id, fiscal_year_id) REFERENCES fiscal_year (tenant_id, company_id, id),
	CONSTRAINT ck_fiscal_period_fiscal_period_version CHECK (row_version > 0),
	CONSTRAINT ck_fiscal_period_fiscal_period_sequence CHECK (sequence BETWEEN 1 AND 12),
	CONSTRAINT ck_fiscal_period_fiscal_period_dates CHECK (end_date >= start_date),
	CONSTRAINT ck_fiscal_period_fiscal_period_status CHECK (status IN ('FUTURE', 'OPEN', 'SOFT_CLOSED', 'CLOSED', 'LOCKED')),
	INDEX ix_fiscal_period_date (tenant_id, company_id, start_date, end_date),
	INDEX ix_fiscal_period_page (tenant_id, company_id, id),
	INDEX ix_fiscal_period_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE fiscal_period"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
