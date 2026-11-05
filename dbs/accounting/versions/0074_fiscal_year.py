"""fiscal_year; indexes and foreign keys created by one atomic DDL."""
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE fiscal_year (
	code VARCHAR(40) NOT NULL,
	start_date DATE NOT NULL,
	end_date DATE NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_fiscal_year PRIMARY KEY (id),
	CONSTRAINT uq_fiscal_year_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_fiscal_year_start UNIQUE (tenant_id, company_id, start_date),
	CONSTRAINT uq_fiscal_year_code UNIQUE (tenant_id, company_id, code),
	CONSTRAINT ck_fiscal_year_fiscal_year_version CHECK (row_version > 0),
	CONSTRAINT ck_fiscal_year_fiscal_year_dates CHECK (end_date >= start_date),
	INDEX ix_fiscal_year_page (tenant_id, company_id, id),
	INDEX ix_fiscal_year_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE fiscal_year"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
