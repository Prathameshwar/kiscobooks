"""Create purchase_price_term; one reversible DDL."""
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE purchase_price_term (
    draft_id BINARY(16) NULL,
    price_id BINARY(16) NULL,
    gross_amount NUMERIC(19,4) NOT NULL,
    discount_kind VARCHAR(20) NOT NULL,
    discount_value NUMERIC(19,4) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_purchase_price_term PRIMARY KEY (id),
    CONSTRAINT uq_v92_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v92_1 UNIQUE (tenant_id, company_id, draft_id),
    CONSTRAINT uq_v92_2 UNIQUE (tenant_id, company_id, price_id),
    CONSTRAINT fk_v92_0 FOREIGN KEY(tenant_id, company_id, currency, draft_id) REFERENCES item_price_draft (tenant_id, company_id, currency, id),
    CONSTRAINT fk_v92_1 FOREIGN KEY(tenant_id, company_id, currency, price_id) REFERENCES item_price (tenant_id, company_id, currency, id),
    CONSTRAINT ck_purchase_price_term_v92_0 CHECK (row_version >= 1),
    CONSTRAINT ck_purchase_price_term_v92_1 CHECK ((draft_id IS NOT NULL AND price_id IS NULL) OR (draft_id IS NULL AND price_id IS NOT NULL)),
    CONSTRAINT ck_purchase_price_term_v92_2 CHECK (gross_amount > 0),
    CONSTRAINT ck_purchase_price_term_v92_3 CHECK (discount_value >= 0),
    CONSTRAINT ck_purchase_price_term_v92_4 CHECK ((discount_kind = 'NONE' AND discount_value = 0) OR (discount_kind = 'PERCENT' AND discount_value <= 100) OR (discount_kind = 'FIXED_PER_BASIS' AND discount_value <= gross_amount)),
    INDEX ix_purchase_price_term_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE purchase_price_term")
