"""Create item_price_numeric_revision; one reversible DDL."""
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_price_numeric_revision (
    item_id BINARY(16) NOT NULL,
    unit_revision_id BINARY(16) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    price_decimal_places INTEGER NOT NULL,
    price_increment NUMERIC(19,4) NULL,
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
    CONSTRAINT pk_item_price_numeric_revision PRIMARY KEY (id),
    CONSTRAINT uq_v87_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v87_1 UNIQUE (tenant_id, company_id, item_id, unit_revision_id, currency, valid_from),
    CONSTRAINT uq_v87_2 UNIQUE (tenant_id, company_id, item_id, unit_revision_id, currency, id),
    CONSTRAINT fk_v87_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_v87_1 FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id),
    CONSTRAINT ck_item_price_numeric_revision_v87_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_price_numeric_revision_v87_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_item_price_numeric_revision_v87_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_item_price_numeric_revision_v87_3 CHECK (price_decimal_places BETWEEN 0 AND 4),
    CONSTRAINT ck_item_price_numeric_revision_v87_4 CHECK (price_increment IS NULL OR price_increment > 0),
    INDEX ix_item_price_numeric_revision_tenant_id (tenant_id),
    INDEX ix_v87_0 (tenant_id, company_id, item_id, unit_revision_id, currency, valid_from, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_price_numeric_revision")
