"""Create item_mrp; one reversible DDL."""
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_mrp (
    item_id BINARY(16) NOT NULL,
    unit_revision_id BINARY(16) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    numeric_revision_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    amount NUMERIC(19,4) NOT NULL,
    price_basis_quantity NUMERIC(19,4) NOT NULL,
    tax_basis VARCHAR(12) NOT NULL,
    source_reference VARCHAR(500) NOT NULL,
    jurisdiction VARCHAR(20) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_mrp PRIMARY KEY (id),
    CONSTRAINT uq_v94_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v94_1 UNIQUE (tenant_id, company_id, item_id, unit_revision_id, currency, jurisdiction, valid_from),
    CONSTRAINT fk_v94_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_v94_1 FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id),
    CONSTRAINT fk_v94_2 FOREIGN KEY(tenant_id, company_id, item_id, unit_revision_id, currency, numeric_revision_id) REFERENCES item_price_numeric_revision (tenant_id, company_id, item_id, unit_revision_id, currency, id),
    CONSTRAINT ck_item_mrp_v94_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_mrp_v94_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_item_mrp_v94_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_item_mrp_v94_3 CHECK (amount > 0),
    CONSTRAINT ck_item_mrp_v94_4 CHECK (price_basis_quantity > 0),
    CONSTRAINT ck_item_mrp_v94_5 CHECK (tax_basis IN ('EXCLUSIVE','INCLUSIVE')),
    CONSTRAINT ck_item_mrp_v94_6 CHECK (tax_basis = 'INCLUSIVE'),
    INDEX ix_item_mrp_tenant_id (tenant_id),
    INDEX ix_v94_0 (tenant_id, company_id, item_id, unit_revision_id, currency, jurisdiction, valid_from, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_mrp")
