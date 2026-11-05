"""Create tax_rule; one reversible DDL."""
from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_rule (
	code VARCHAR(30) NOT NULL,
	name VARCHAR(100) NOT NULL,
	tax_system VARCHAR(10) NOT NULL,
	jurisdiction VARCHAR(2) NOT NULL,
	item_kind VARCHAR(7) NOT NULL,
	treatment VARCHAR(10) NOT NULL,
	tax_category_id BINARY(16) NOT NULL,
	is_active BOOL NOT NULL,
	custom_fields JSON NULL,
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
	CONSTRAINT pk_tax_rule PRIMARY KEY (id),
	CONSTRAINT uq_tax_rule_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rule_version CHECK (row_version >= 1),
	CONSTRAINT uq_tax_rule_code UNIQUE (tenant_id, company_id, code),
	CONSTRAINT fk_tax_rule_tax_category_id FOREIGN KEY(tenant_id, company_id, tax_category_id) REFERENCES tax_category (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rule_jurisdiction CHECK (tax_system = 'gst_in' AND jurisdiction = 'IN'),
	CONSTRAINT ck_tax_rule_kind CHECK (item_kind IN ('GOODS','SERVICE')),
	CONSTRAINT ck_tax_rule_treatment CHECK (treatment IN ('TAXABLE','NIL_RATED','EXEMPT','NON_GST')),
    INDEX ix_tax_rule_name (tenant_id, company_id, name, id),
    INDEX ix_tax_rule_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE tax_rule")
