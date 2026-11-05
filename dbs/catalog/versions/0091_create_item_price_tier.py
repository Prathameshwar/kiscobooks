"""Create item_price_tier; one reversible DDL."""
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_price_tier (
    draft_id BINARY(16) NULL,
    price_id BINARY(16) NULL,
    min_quantity NUMERIC(19,4) NOT NULL,
    max_quantity NUMERIC(19,4) NULL,
    amount NUMERIC(19,4) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_price_tier PRIMARY KEY (id),
    CONSTRAINT uq_v91_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v91_1 UNIQUE (tenant_id, company_id, draft_id, min_quantity),
    CONSTRAINT uq_v91_2 UNIQUE (tenant_id, company_id, price_id, min_quantity),
    CONSTRAINT fk_v91_0 FOREIGN KEY(tenant_id, company_id, currency, draft_id) REFERENCES item_price_draft (tenant_id, company_id, currency, id),
    CONSTRAINT fk_v91_1 FOREIGN KEY(tenant_id, company_id, currency, price_id) REFERENCES item_price (tenant_id, company_id, currency, id),
    CONSTRAINT ck_item_price_tier_v91_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_price_tier_v91_1 CHECK ((draft_id IS NOT NULL AND price_id IS NULL) OR (draft_id IS NULL AND price_id IS NOT NULL)),
    CONSTRAINT ck_item_price_tier_v91_2 CHECK (min_quantity >= 0),
    CONSTRAINT ck_item_price_tier_v91_3 CHECK (max_quantity IS NULL OR max_quantity > min_quantity),
    CONSTRAINT ck_item_price_tier_v91_4 CHECK (amount >= 0),
    INDEX ix_item_price_tier_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_price_tier")
