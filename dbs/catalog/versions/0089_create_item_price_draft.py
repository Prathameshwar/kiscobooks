"""Create item_price_draft; one reversible DDL."""
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_price_draft (
    item_id BINARY(16) NOT NULL,
    unit_revision_id BINARY(16) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    numeric_revision_id BINARY(16) NOT NULL,
    series_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    price_method VARCHAR(10) NOT NULL,
    amount NUMERIC(19,4) NULL,
    price_basis_quantity NUMERIC(19,4) NOT NULL,
    source_reference VARCHAR(500) NOT NULL,
    status VARCHAR(12) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_price_draft PRIMARY KEY (id),
    CONSTRAINT uq_v89_currency UNIQUE (tenant_id, company_id, currency, id),
    CONSTRAINT uq_v89_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT fk_v89_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_v89_1 FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id),
    CONSTRAINT fk_v89_2 FOREIGN KEY(tenant_id, company_id, item_id, unit_revision_id, currency, numeric_revision_id) REFERENCES item_price_numeric_revision (tenant_id, company_id, item_id, unit_revision_id, currency, id),
    CONSTRAINT fk_v89_3 FOREIGN KEY(tenant_id, company_id, item_id, unit_revision_id, currency, series_id) REFERENCES item_price_series (tenant_id, company_id, item_id, unit_revision_id, currency, id),
    CONSTRAINT ck_item_price_draft_v89_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_price_draft_v89_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_item_price_draft_v89_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_item_price_draft_v89_3 CHECK (price_basis_quantity > 0),
    CONSTRAINT ck_item_price_draft_v89_4 CHECK ((price_method = 'FIXED' AND amount IS NOT NULL AND amount >= 0) OR (price_method IN ('TIERS','FORMULA') AND amount IS NULL)),
    CONSTRAINT ck_item_price_draft_v89_5 CHECK (status IN ('DRAFT','PUBLISHED')),
    INDEX ix_item_price_draft_tenant_id (tenant_id),
    INDEX ix_v89_0 (tenant_id, company_id, series_id, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_price_draft")
