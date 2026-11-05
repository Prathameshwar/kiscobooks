"""financial_setup; indexes and foreign keys created by one atomic DDL."""
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE financial_setup (
	base_currency VARCHAR(3) NOT NULL,
	books_begin_date DATE NOT NULL,
	fiscal_year_start_month INTEGER NOT NULL,
	fiscal_year_start_day INTEGER NOT NULL,
	amount_precision INTEGER NOT NULL,
	rounding_mode VARCHAR(20) NOT NULL,
	timezone VARCHAR(100) NOT NULL,
	configuration_hash VARCHAR(64) NOT NULL,
	first_posted_at DATETIME(6),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_financial_setup PRIMARY KEY (id),
	CONSTRAINT uq_financial_setup_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_financial_setup_company UNIQUE (tenant_id, company_id),
	CONSTRAINT ck_financial_setup_financial_setup_version CHECK (row_version > 0),
	CONSTRAINT ck_financial_setup_financial_setup_precision CHECK (amount_precision BETWEEN 0 AND 4),
	CONSTRAINT ck_financial_setup_financial_setup_calendar CHECK (fiscal_year_start_month BETWEEN 1 AND 12 AND fiscal_year_start_day BETWEEN 1 AND 31),
	CONSTRAINT ck_financial_setup_financial_setup_rounding CHECK (rounding_mode IN ('half_up', 'half_even', 'down')),
	INDEX ix_financial_setup_page (tenant_id, company_id, id),
	INDEX ix_financial_setup_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE financial_setup"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
