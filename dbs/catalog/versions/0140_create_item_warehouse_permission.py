"""Create item_warehouse_permission; one atomic DDL, with a paired model."""

from alembic import op

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_warehouse_permission (
    item_id BINARY(16) NOT NULL,
    warehouse_id BINARY(16) NOT NULL,
    is_active BOOL NOT NULL,
    allow_sale_issue BOOL NOT NULL,
    allow_purchase_receipt BOOL NOT NULL,
    allow_transfer_in BOOL NOT NULL,
    allow_transfer_out BOOL NOT NULL,
    allow_customer_return_receipt BOOL NOT NULL,
    allow_supplier_return_issue BOOL NOT NULL,
    allow_opening_stock BOOL NOT NULL,
    allow_adjustment BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_item_warehouse_permission_flags CHECK (allow_sale_issue IN (0,1)
        AND allow_purchase_receipt IN (0,1) AND allow_transfer_in IN (0,1)
        AND allow_transfer_out IN (0,1) AND allow_customer_return_receipt IN (0,1)
        AND allow_supplier_return_issue IN (0,1) AND allow_opening_stock IN (0,1)
        AND allow_adjustment IN (0,1)),
    CONSTRAINT ck_item_warehouse_permission_row_version CHECK (row_version >= 1),
    CONSTRAINT fk_item_warehouse_perm_location FOREIGN KEY(tenant_id, company_id, warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_item_warehouse_perm_policy FOREIGN KEY(tenant_id, company_id, item_id)
        REFERENCES item_warehouse_policy (tenant_id, company_id, item_id),
    CONSTRAINT pk_item_warehouse_permission PRIMARY KEY (id),
    CONSTRAINT uq_item_warehouse_perm_scope UNIQUE (tenant_id, company_id, item_id, warehouse_id),
    CONSTRAINT uq_item_warehouse_perm_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_item_warehouse_perm_location (tenant_id, company_id, warehouse_id, is_active),
    KEY ix_item_warehouse_permission_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_warehouse_permission")
