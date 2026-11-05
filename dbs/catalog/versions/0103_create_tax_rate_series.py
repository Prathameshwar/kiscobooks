"""Create tax_rate_series; one reversible DDL."""
from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_rate_series (
	rule_id BINARY(16) NOT NULL,
	applicability VARCHAR(12) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_rate_series PRIMARY KEY (id),
	CONSTRAINT uq_tax_rate_series_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rate_series_version CHECK (row_version >= 1),
	CONSTRAINT fk_tax_rate_series_rule_id FOREIGN KEY(tenant_id, company_id, rule_id) REFERENCES tax_rule (tenant_id, company_id, id),
	CONSTRAINT uq_tax_rate_series_context UNIQUE (tenant_id, company_id, rule_id, applicability),
	CONSTRAINT ck_tax_rate_series_applicability CHECK (applicability IN ('INTRA_STATE','INTRA_UT','INTER_STATE')),
    INDEX ix_tax_rate_series_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE tax_rate_series")
