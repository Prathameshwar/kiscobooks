"""Create item_barcode; one reversible DDL."""
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_barcode (
    item_id BINARY(16) NOT NULL,
    binding_id BINARY(16) NULL,
    value VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
    symbology VARCHAR(12) NOT NULL,
    is_active BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item_barcode PRIMARY KEY (id),
    CONSTRAINT uq_p80_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_p80_1 UNIQUE (tenant_id, company_id, value),
    CONSTRAINT fk_p80_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id,
        company_id, id),
    CONSTRAINT fk_p80_1 FOREIGN KEY(tenant_id, company_id, item_id, binding_id) REFERENCES
        item_unit_binding (tenant_id, company_id, item_id, id),
    CONSTRAINT ck_item_barcode_p80_check_0 CHECK (row_version >= 1),
    CONSTRAINT ck_item_barcode_p80_check_1 CHECK (symbology IN ('GTIN','CODE128','QR')),
    INDEX ix_item_barcode_tenant_id (tenant_id),
    INDEX ix_p80_0 (tenant_id, company_id, item_id, id),
    INDEX ix_p80_1 (tenant_id, company_id, binding_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_barcode")
