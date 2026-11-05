"""Create native promotion-limit definition storage; one reversible DDL."""
from alembic import op

revision = "0207"
down_revision = "0206"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_limit_definition (
	scope_kind VARCHAR(12) NOT NULL, 
	metric VARCHAR(20) NOT NULL, 
	period_basis VARCHAR(12) NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	currency VARCHAR(3) NULL,
	unit_id BINARY(16) NULL,
	company_id BINARY(16) NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	is_active BOOL NOT NULL, 
	deactivated_at DATETIME(6) NULL,
	deactivated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_limit_definition PRIMARY KEY (id), 
	CONSTRAINT uq_promotion_limit_definition_scope_id UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_promotion_limit_definition_scope_code UNIQUE (tenant_id, company_id, code), 
	CONSTRAINT ck_promotion_limit_definition_promotion_limit_definition_version CHECK (row_version >= 1), 
	CONSTRAINT ck_promotion_limit_definition_scope CHECK (scope_kind IN ('CAMPAIGN','PROMOTION','PROGRAM')), 
	CONSTRAINT ck_promotion_limit_definition_metric CHECK (metric IN ('TOTAL_USES','PER_CUSTOMER_USES','PER_ORDER_USES','REWARD_UNITS','BUDGET')), 
	CONSTRAINT ck_promotion_limit_definition_period CHECK (period_basis IN ('LIFETIME','DAY','MONTH','YEAR','ORDER')), 
	CONSTRAINT ck_promotion_limit_definition_order_period CHECK ((metric = 'PER_ORDER_USES' AND period_basis = 'ORDER') OR (metric <> 'PER_ORDER_USES' AND period_basis <> 'ORDER')), 
	CONSTRAINT ck_promotion_limit_definition_measure CHECK ((metric = 'BUDGET' AND currency IS NOT NULL AND unit_id IS NULL) OR (metric = 'REWARD_UNITS' AND currency IS NULL AND unit_id IS NOT NULL) OR (metric IN ('TOTAL_USES','PER_CUSTOMER_USES','PER_ORDER_USES') AND currency IS NULL AND unit_id IS NULL)), 
	CONSTRAINT fk_promotion_limit_unit FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES unit_of_measure (tenant_id, company_id, id),
	KEY ix_promotion_limit_definition_scope (tenant_id, company_id, scope_kind, id),
	KEY ix_promotion_limit_definition_metric (tenant_id, company_id, metric, id),
	KEY ix_promotion_limit_definition_unit (tenant_id, company_id, unit_id),
	KEY ix_promotion_limit_definition_active_code (tenant_id, company_id, is_active, code, id),
	KEY ix_promotion_limit_definition_active_name (tenant_id, company_id, is_active, name, id),
	KEY ix_promotion_limit_definition_name (tenant_id, company_id, name, id),
	KEY ix_promotion_limit_definition_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE promotion_limit_definition")
