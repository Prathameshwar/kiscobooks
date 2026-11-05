"""Create warehouse_operation_policy_revision; one atomic DDL, with a paired model."""

from alembic import op

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE warehouse_operation_policy_revision (
    warehouse_id BINARY(16) NOT NULL,
    revision INTEGER NOT NULL,
    effective_from DATETIME(6) NOT NULL,
    effective_to DATETIME(6) NULL,
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
    CONSTRAINT ck_warehouse_operation_policy_revision_flags CHECK (allow_sale_issue IN (0,1)
        AND allow_purchase_receipt IN (0,1) AND allow_transfer_in IN (0,1)
        AND allow_transfer_out IN (0,1) AND allow_customer_return_receipt IN (0,1)
        AND allow_supplier_return_issue IN (0,1) AND allow_opening_stock IN (0,1)
        AND allow_adjustment IN (0,1)),
    CONSTRAINT ck_warehouse_operation_policy_revision_version CHECK (revision >= 1
        AND row_version >= 1),
    CONSTRAINT ck_warehouse_operation_policy_revision_window CHECK (effective_to IS NULL
        OR effective_to >= effective_from),
    CONSTRAINT fk_warehouse_policy_rev_parent FOREIGN KEY(tenant_id, company_id, warehouse_id)
        REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT pk_warehouse_operation_policy_revision PRIMARY KEY (id),
    CONSTRAINT uq_warehouse_policy_rev_number UNIQUE (tenant_id, company_id, warehouse_id,
        revision),
    CONSTRAINT uq_warehouse_policy_rev_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_warehouse_operation_policy_revision_tenant_id (tenant_id),
    KEY ix_warehouse_policy_rev_window (tenant_id, company_id, warehouse_id, effective_to,
        revision, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE warehouse_operation_policy_revision")
