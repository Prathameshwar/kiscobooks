"""Create tax_rate; one reversible DDL."""
from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_rate (
	series_id BINARY(16) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE NULL,
	supersedes_id BINARY(16) NULL,
	source_reference VARCHAR(500) NOT NULL,
	source_url VARCHAR(1000) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_rate PRIMARY KEY (id),
	CONSTRAINT uq_tax_rate_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rate_version CHECK (row_version >= 1),
	CONSTRAINT ck_tax_rate_start CHECK (valid_from >= '1000-01-01'),
	CONSTRAINT ck_tax_rate_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	CONSTRAINT uq_tax_rate_start UNIQUE (tenant_id, company_id, series_id, valid_from),
	CONSTRAINT fk_tax_rate_series_id FOREIGN KEY(tenant_id, company_id, series_id) REFERENCES tax_rate_series (tenant_id, company_id, id),
	CONSTRAINT fk_tax_rate_supersedes_id FOREIGN KEY(tenant_id, company_id, supersedes_id) REFERENCES tax_rate (tenant_id, company_id, id),
    INDEX ix_tax_rate_date (tenant_id, company_id, series_id, valid_from, id),
    INDEX ix_tax_rate_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE tax_rate")
