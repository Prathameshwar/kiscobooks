"""account_tax_default: account GST defaults master; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE account_tax_default (
	account_id BINARY(16) NOT NULL,
	direction VARCHAR(8) NOT NULL,
	supply_kind VARCHAR(7) NOT NULL,
	code_system VARCHAR(3) NOT NULL,
	code VARCHAR(8) NOT NULL,
	rule_id BINARY(16),
	treatment VARCHAR(10) NOT NULL,
	itc_eligibility VARCHAR(10),
	rcm_applicable BOOL NOT NULL,
	assessable_inclusion VARCHAR(8) NOT NULL,
	apportion_by VARCHAR(8),
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
	CONSTRAINT pk_account_tax_default PRIMARY KEY (id),
	CONSTRAINT ck_account_tax_default_account_tax_default_apportion CHECK ((assessable_inclusion = 'NONE' AND apportion_by IS NULL) OR (assessable_inclusion <> 'NONE' AND apportion_by IN ('VALUE', 'QUANTITY'))),
	CONSTRAINT fk_account_tax_default_rule_id FOREIGN KEY(tenant_id, company_id, rule_id) REFERENCES tax_rule_replica (tenant_id, company_id, id),
	CONSTRAINT ck_account_tax_default_account_tax_default_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	CONSTRAINT uq_account_tax_default_0 UNIQUE (tenant_id, company_id, account_id, direction, valid_from),
	CONSTRAINT ck_account_tax_default_account_tax_default_version CHECK (row_version > 0),
	CONSTRAINT ck_account_tax_default_account_tax_default_kind CHECK ((code_system = 'HSN' AND supply_kind = 'GOODS') OR (code_system = 'SAC' AND supply_kind = 'SERVICE')),
	CONSTRAINT fk_account_tax_default_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT uq_account_tax_default_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_account_tax_default_account_tax_default_values CHECK (direction IN ('SALE', 'PURCHASE') AND treatment IN ('TAXABLE', 'NIL_RATED', 'EXEMPT', 'NON_GST') AND assessable_inclusion IN ('NONE', 'GOODS', 'SERVICES', 'BOTH') AND (itc_eligibility IS NULL OR itc_eligibility IN ('ELIGIBLE', 'INELIGIBLE', 'BLOCKED'))),
	INDEX ix_account_tax_default_asof (tenant_id, company_id, valid_from, id),
	INDEX ix_account_tax_default_code (tenant_id, company_id, code, id),
	INDEX ix_account_tax_default_page (tenant_id, company_id, id),
	INDEX ix_account_tax_default_ref0 (tenant_id, company_id, rule_id),
	INDEX ix_account_tax_default_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE account_tax_default"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
