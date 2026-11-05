"""Create item_replenishment_policy; one atomic DDL, with a paired model."""

from alembic import op

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_replenishment_policy (
    item_id BINARY(16) NOT NULL,
    scope_warehouse_id BINARY(16) NOT NULL,
    warehouse_id BINARY(16) NULL,
    purchase_binding_id BINARY(16) NOT NULL,
    safety_quantity NUMERIC(19,4) NOT NULL,
    reorder_quantity NUMERIC(19,4) NOT NULL,
    target_quantity NUMERIC(19,4) NOT NULL,
    min_order_quantity NUMERIC(19,4) NOT NULL,
    max_order_quantity NUMERIC(19,4) NULL,
    order_multiple NUMERIC(19,4) NOT NULL,
    lead_time_days INTEGER NOT NULL,
    is_active BOOL NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_item_replenishment_policy_quantities CHECK (safety_quantity >= 0
        AND reorder_quantity >= safety_quantity AND target_quantity >= reorder_quantity
        AND target_quantity > 0 AND min_order_quantity > 0 AND order_multiple > 0
        AND (max_order_quantity IS NULL OR max_order_quantity >= min_order_quantity)),
    CONSTRAINT ck_item_replenishment_policy_scope CHECK ((warehouse_id IS NULL
        AND scope_warehouse_id = X'00000000000000000000000000000000')
        OR (warehouse_id IS NOT NULL AND scope_warehouse_id = warehouse_id)),
    CONSTRAINT ck_item_replenishment_policy_version CHECK (row_version >= 1
        AND lead_time_days BETWEEN 0 AND 3650),
    CONSTRAINT fk_item_replenishment_item FOREIGN KEY(tenant_id, company_id, item_id)
        REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_item_replenishment_location FOREIGN KEY(tenant_id, company_id, warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_item_replenishment_unit FOREIGN KEY(tenant_id, company_id, item_id,
        purchase_binding_id)
        REFERENCES item_unit_binding (tenant_id, company_id, item_id, id),
    CONSTRAINT pk_item_replenishment_policy PRIMARY KEY (id),
    CONSTRAINT uq_item_replenishment_scope UNIQUE (tenant_id, company_id, item_id,
        scope_warehouse_id),
    CONSTRAINT uq_item_replenishment_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_item_replenishment_location (tenant_id, company_id, warehouse_id, is_active),
    KEY ix_item_replenishment_policy_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_replenishment_policy")
