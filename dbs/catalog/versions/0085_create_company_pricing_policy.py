"""Create company_pricing_policy; one reversible DDL."""
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_pricing_policy (
    default_level_id BINARY(16) NOT NULL,
    missing_price_policy VARCHAR(10) NOT NULL,
    fallback_level_id BINARY(16) NULL,
    purchase_plan_id BINARY(16) NULL,
    sale_unit_mode VARCHAR(24) NOT NULL,
    purchase_unit_mode VARCHAR(24) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_pricing_policy PRIMARY KEY (id),
    CONSTRAINT uq_v85_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v85_1 UNIQUE (tenant_id, company_id, valid_from),
    CONSTRAINT fk_v85_0 FOREIGN KEY(tenant_id, company_id, default_level_id) REFERENCES price_level (tenant_id, company_id, id),
    CONSTRAINT fk_v85_1 FOREIGN KEY(tenant_id, company_id, fallback_level_id) REFERENCES price_level (tenant_id, company_id, id),
    CONSTRAINT fk_v85_2 FOREIGN KEY(tenant_id, company_id, purchase_plan_id) REFERENCES price_plan (tenant_id, company_id, id),
    CONSTRAINT ck_company_pricing_policy_v85_0 CHECK (row_version >= 1),
    CONSTRAINT ck_company_pricing_policy_v85_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_company_pricing_policy_v85_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_company_pricing_policy_v85_3 CHECK ((missing_price_policy = 'ERROR' AND fallback_level_id IS NULL) OR (missing_price_policy = 'FALLBACK' AND fallback_level_id IS NOT NULL AND fallback_level_id <> default_level_id)),
    CONSTRAINT ck_company_pricing_policy_v85_4 CHECK (sale_unit_mode IN ('EXPLICIT_ONLY','EXACT_BASE_DERIVATION')),
    CONSTRAINT ck_company_pricing_policy_v85_5 CHECK (purchase_unit_mode IN ('EXPLICIT_ONLY','EXACT_BASE_DERIVATION')),
    INDEX ix_company_pricing_policy_tenant_id (tenant_id),
    INDEX ix_v85_0 (tenant_id, company_id, valid_from, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE company_pricing_policy")
