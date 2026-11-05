"""Create item; one atomic DDL paired with its native model."""

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item (
    company_id BINARY(16) NOT NULL,
    family_id BINARY(16) NOT NULL,
    default_slot INTEGER NULL,
    sku VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    base_unit_id BINARY(16) NOT NULL,
    sellable BOOL NOT NULL,
    purchasable BOOL NOT NULL,
    min_sale_quantity NUMERIC(19,4) NULL,
    status VARCHAR(20) NOT NULL,
    row_version INTEGER NOT NULL,
    custom_fields JSON NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_item PRIMARY KEY (id),
    CONSTRAINT uq_item_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_item_sku UNIQUE (tenant_id, company_id, sku),
    CONSTRAINT uq_item_default UNIQUE (tenant_id, company_id, family_id, default_slot),
    CONSTRAINT fk_item_family FOREIGN KEY(tenant_id, company_id, family_id) REFERENCES product_family (tenant_id, company_id, id),
    CONSTRAINT fk_item_base_unit FOREIGN KEY(tenant_id, company_id, base_unit_id) REFERENCES unit_of_measure (tenant_id, company_id, id),
    CONSTRAINT ck_item_item_default_slot CHECK (default_slot IS NULL OR default_slot = 1),
    CONSTRAINT ck_item_item_status CHECK (status IN ('DRAFT', 'ACTIVE', 'DISCONTINUED')),
    CONSTRAINT ck_item_item_min_sale_quantity CHECK (min_sale_quantity IS NULL OR min_sale_quantity > 0),
    CONSTRAINT ck_item_item_version CHECK (row_version >= 1),
    KEY ix_item_family (tenant_id, company_id, family_id, sku, id),
    KEY ix_item_name (tenant_id, company_id, name, id),
    KEY ix_item_tenant_id (tenant_id),
    KEY ix_item_unit (tenant_id, company_id, base_unit_id, id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item")
