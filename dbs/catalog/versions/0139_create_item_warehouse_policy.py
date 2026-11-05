"""Create item_warehouse_policy; one atomic DDL, with a paired model."""

from alembic import op

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_warehouse_policy (
    item_id BINARY(16) NOT NULL,
    selection_mode VARCHAR(20) NOT NULL,
    default_sale_warehouse_id BINARY(16) NULL,
    default_purchase_warehouse_id BINARY(16) NULL,
    default_customer_return_warehouse_id BINARY(16) NULL,
    default_opening_warehouse_id BINARY(16) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_item_warehouse_policy_row_version CHECK (row_version >= 1),
    CONSTRAINT ck_item_warehouse_policy_selection_mode CHECK (selection_mode
        IN ('ALLOW_ALL_ACTIVE','ALLOW_LIST')),
    CONSTRAINT fk_item_warehouse_policy_customer_return FOREIGN KEY(tenant_id, company_id,
        default_customer_return_warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_item_warehouse_policy_item FOREIGN KEY(tenant_id, company_id, item_id)
        REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_item_warehouse_policy_opening FOREIGN KEY(tenant_id, company_id,
        default_opening_warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_item_warehouse_policy_purchase FOREIGN KEY(tenant_id, company_id,
        default_purchase_warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_item_warehouse_policy_sale FOREIGN KEY(tenant_id, company_id,
        default_sale_warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT pk_item_warehouse_policy PRIMARY KEY (id),
    CONSTRAINT uq_item_warehouse_policy_item UNIQUE (tenant_id, company_id, item_id),
    CONSTRAINT uq_item_warehouse_policy_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_item_warehouse_policy_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE item_warehouse_policy")
