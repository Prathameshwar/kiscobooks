"""Create price_plan; one reversible DDL."""
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE price_plan (
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    purpose VARCHAR(20) NOT NULL,
    price_level_id BINARY(16) NULL,
    currency VARCHAR(3) NOT NULL,
    tax_basis VARCHAR(12) NOT NULL,
    custom_fields JSON NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_price_plan PRIMARY KEY (id),
    CONSTRAINT uq_v84_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v84_1 UNIQUE (tenant_id, company_id, code),
    CONSTRAINT uq_v84_2 UNIQUE (tenant_id, company_id, price_level_id, currency),
    CONSTRAINT uq_v84_3 UNIQUE (tenant_id, company_id, id, currency),
    CONSTRAINT fk_v84_0 FOREIGN KEY(tenant_id, company_id, price_level_id) REFERENCES price_level (tenant_id, company_id, id),
    CONSTRAINT ck_price_plan_v84_0 CHECK (row_version >= 1),
    CONSTRAINT ck_price_plan_v84_1 CHECK (purpose IN ('SALE','PURCHASE','REFERENCE_RETAIL')),
    CONSTRAINT ck_price_plan_v84_2 CHECK ((purpose = 'SALE' AND price_level_id IS NOT NULL) OR (purpose <> 'SALE' AND price_level_id IS NULL)),
    CONSTRAINT ck_price_plan_v84_3 CHECK (tax_basis IN ('EXCLUSIVE','INCLUSIVE')),
    INDEX ix_price_plan_tenant_id (tenant_id),
    INDEX ix_v84_0 (tenant_id, company_id, purpose, currency, id),
    INDEX ix_v84_1 (tenant_id, company_id, name, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE price_plan")
