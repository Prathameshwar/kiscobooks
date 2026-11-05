"""Create item_price_formula; one reversible DDL."""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_price_formula (
    draft_id BINARY(16) NULL,
    price_id BINARY(16) NULL,
    recipe VARCHAR(32) NOT NULL,
    percentage NUMERIC(19,4) NOT NULL,
    estimate_kind VARCHAR(24) NULL,
    jurisdiction VARCHAR(20) NULL,
    rounding_mode VARCHAR(10) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_price_formula PRIMARY KEY (id),
    CONSTRAINT uq_v95_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v95_1 UNIQUE (tenant_id, company_id, draft_id),
    CONSTRAINT uq_v95_2 UNIQUE (tenant_id, company_id, price_id),
    CONSTRAINT fk_v95_0 FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES item_price_draft (tenant_id, company_id, id),
    CONSTRAINT fk_v95_1 FOREIGN KEY(tenant_id, company_id, price_id) REFERENCES item_price (tenant_id, company_id, id),
    CONSTRAINT ck_item_price_formula_v95_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_price_formula_v95_1 CHECK ((draft_id IS NOT NULL AND price_id IS NULL) OR (draft_id IS NULL AND price_id IS NOT NULL)),
    CONSTRAINT ck_item_price_formula_v95_2 CHECK (percentage >= 0),
    CONSTRAINT ck_item_price_formula_v95_3 CHECK ((recipe = 'MRP_LESS_PERCENT' AND percentage <= 100 AND jurisdiction IS NOT NULL AND estimate_kind IS NULL) OR (recipe IN ('REFERENCE_COST_PLUS_MARKUP','REFERENCE_COST_TARGET_MARGIN') AND estimate_kind IS NOT NULL AND jurisdiction IS NULL)),
    CONSTRAINT ck_item_price_formula_v95_4 CHECK (recipe <> 'REFERENCE_COST_TARGET_MARGIN' OR percentage < 100),
    CONSTRAINT ck_item_price_formula_v95_5 CHECK (rounding_mode IN ('HALF_UP','UP','DOWN')),
    INDEX ix_item_price_formula_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_price_formula")
