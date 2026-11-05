"""Create item_price_series; one reversible DDL."""
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_price_series (
    item_id BINARY(16) NOT NULL,
    unit_revision_id BINARY(16) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    plan_id BINARY(16) NOT NULL,
    price_scope_id BINARY(16) NOT NULL,
    audience_kind VARCHAR(8) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_price_series PRIMARY KEY (id),
    CONSTRAINT uq_v88_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v88_1 UNIQUE (tenant_id, company_id, plan_id, price_scope_id, unit_revision_id),
    CONSTRAINT uq_v88_2 UNIQUE (tenant_id, company_id, item_id, unit_revision_id, currency, id),
    CONSTRAINT fk_v88_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_v88_1 FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id),
    CONSTRAINT fk_v88_2 FOREIGN KEY(tenant_id, company_id, plan_id, currency) REFERENCES price_plan (tenant_id, company_id, id, currency),
    CONSTRAINT fk_v88_3 FOREIGN KEY(tenant_id, company_id, item_id, price_scope_id) REFERENCES item_price_scope (tenant_id, company_id, item_id, id),
    CONSTRAINT ck_item_price_series_v88_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_price_series_v88_1 CHECK (audience_kind = 'STANDARD'),
    INDEX ix_item_price_series_tenant_id (tenant_id),
    INDEX ix_v88_0 (tenant_id, company_id, item_id, plan_id, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_price_series")
