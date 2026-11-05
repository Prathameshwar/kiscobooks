"""Create company_warehouse_configuration; one atomic DDL, with a paired model."""

from alembic import op

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_warehouse_configuration (
    main_warehouse_id BINARY(16) NOT NULL,
    transit_warehouse_id BINARY(16) NOT NULL,
    default_sale_warehouse_id BINARY(16) NULL,
    default_purchase_warehouse_id BINARY(16) NULL,
    default_customer_return_warehouse_id BINARY(16) NULL,
    default_opening_warehouse_id BINARY(16) NULL,
    source_version BIGINT NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_company_warehouse_configuration_custody
        CHECK (main_warehouse_id <> transit_warehouse_id),
    CONSTRAINT ck_company_warehouse_configuration_row_version CHECK (row_version >= 1),
    CONSTRAINT ck_company_warehouse_configuration_source_version CHECK (source_version > 0),
    CONSTRAINT fk_company_warehouse_configuration_customer_return FOREIGN KEY(tenant_id,
        company_id, default_customer_return_warehouse_id) REFERENCES warehouse (tenant_id,
        company_id, id),
    CONSTRAINT fk_company_warehouse_configuration_main FOREIGN KEY(tenant_id, company_id,
        main_warehouse_id) REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_company_warehouse_configuration_opening FOREIGN KEY(tenant_id, company_id,
        default_opening_warehouse_id) REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_company_warehouse_configuration_purchase FOREIGN KEY(tenant_id, company_id,
        default_purchase_warehouse_id) REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_company_warehouse_configuration_sale FOREIGN KEY(tenant_id, company_id,
        default_sale_warehouse_id) REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT fk_company_warehouse_configuration_transit FOREIGN KEY(tenant_id, company_id,
        transit_warehouse_id) REFERENCES warehouse (tenant_id, company_id, id),
    CONSTRAINT pk_company_warehouse_configuration PRIMARY KEY (id),
    CONSTRAINT uq_company_warehouse_configuration_company UNIQUE (tenant_id, company_id),
    CONSTRAINT uq_company_warehouse_configuration_scope_id UNIQUE (tenant_id, company_id, id),
    KEY ix_company_warehouse_configuration_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_warehouse_configuration")
