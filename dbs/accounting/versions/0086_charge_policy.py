"""charge_policy; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE charge_policy (
	account_id BINARY(16) NOT NULL,
	offset_account_id BINARY(16) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE,
	accrual_start_date DATE NOT NULL,
	method VARCHAR(20) NOT NULL,
	rate NUMERIC(19, 4) NOT NULL,
	rate_period VARCHAR(20) NOT NULL,
	compound VARCHAR(20) NOT NULL,
	basis VARCHAR(20) NOT NULL,
	day_basis INTEGER NOT NULL,
	grace_days INTEGER NOT NULL,
	minimum NUMERIC(19, 4) NOT NULL,
	cap NUMERIC(19, 4),
	charge_on_charge BOOL NOT NULL,
	tax_treatment VARCHAR(20) NOT NULL,
	tax_reason VARCHAR(500) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_charge_policy PRIMARY KEY (id),
	CONSTRAINT uq_charge_policy_effective UNIQUE (tenant_id, company_id, account_id, currency, valid_from),
	CONSTRAINT ck_charge_policy_charge_policy_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	CONSTRAINT ck_charge_policy_charge_policy_method CHECK (method IN ('FIXED', 'INTEREST') AND compound IN ('SIMPLE', 'DAILY')),
	CONSTRAINT ck_charge_policy_charge_policy_amount CHECK (rate > 0 AND minimum >= 0 AND (cap IS NULL OR cap >= minimum)),
	CONSTRAINT ck_charge_policy_charge_policy_days CHECK (day_basis IN (360,365) AND grace_days BETWEEN 0 AND 3650),
	CONSTRAINT uq_charge_policy_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_charge_policy_charge_policy_version CHECK (row_version > 0),
	CONSTRAINT fk_charge_policy_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_charge_policy_offset_account_id FOREIGN KEY(tenant_id, company_id, offset_account_id) REFERENCES account (tenant_id, company_id, id),
	INDEX ix_charge_policy_asof (tenant_id, company_id, account_id, currency, valid_from, valid_to),
	INDEX ix_charge_policy_page (tenant_id, company_id, id),
	INDEX ix_charge_policy_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE charge_policy"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
