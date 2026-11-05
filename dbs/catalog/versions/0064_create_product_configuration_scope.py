"""Create product_configuration_scope; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE product_configuration_scope (
    scope_kind VARCHAR(10) NOT NULL,
    owner_id BINARY(16) NOT NULL,
    product_type_id BINARY(16) NULL,
    group_id BINARY(16) NULL,
    family_id BINARY(16) NULL,
    item_id BINARY(16) NULL,
    row_version INTEGER NOT NULL,
    latest_revision INTEGER NOT NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_product_configuration_scope PRIMARY KEY (id),
    CONSTRAINT uq_product_configuration_scope_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_product_configuration_scope_owner UNIQUE (tenant_id, company_id, scope_kind,
        owner_id),
    CONSTRAINT fk_configuration_scope_type FOREIGN KEY(tenant_id, company_id, product_type_id)
        REFERENCES product_type (tenant_id, company_id, id),
    CONSTRAINT fk_configuration_scope_group FOREIGN KEY(tenant_id, company_id, group_id)
        REFERENCES item_group (tenant_id, company_id, id),
    CONSTRAINT ck_product_configuration_scope_configuration_scope_owner CHECK ((scope_kind =
        'COMPANY' AND owner_id = company_id AND product_type_id IS NULL AND group_id IS NULL AND
        family_id IS NULL AND item_id IS NULL) OR (scope_kind = 'TYPE' AND owner_id =
        product_type_id AND product_type_id IS NOT NULL AND group_id IS NULL AND family_id IS
        NULL AND item_id IS NULL) OR (scope_kind = 'GROUP' AND owner_id = group_id AND
        product_type_id IS NULL AND group_id IS NOT NULL AND family_id IS NULL AND item_id IS
        NULL) OR (scope_kind = 'FAMILY' AND owner_id = family_id AND product_type_id IS NULL AND
        group_id IS NULL AND family_id IS NOT NULL AND item_id IS NULL) OR (scope_kind = 'SKU'
        AND owner_id = item_id AND product_type_id IS NULL AND group_id IS NULL AND family_id IS
        NULL AND item_id IS NOT NULL)),
    CONSTRAINT ck_product_configuration_scope_configuration_scope_version CHECK (row_version >=
        1 AND latest_revision >= 0),
    CONSTRAINT fk_config_scope_family_id FOREIGN KEY(tenant_id, company_id, family_id)
        REFERENCES product_family (tenant_id, company_id, id),
    CONSTRAINT fk_config_scope_item_id FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES
        item (tenant_id, company_id, id),
    INDEX ix_config_scope_family_id (tenant_id, company_id, family_id, id),
    INDEX ix_config_scope_item_id (tenant_id, company_id, item_id, id),
    INDEX ix_configuration_scope_group (tenant_id, company_id, group_id, id),
    INDEX ix_configuration_scope_kind (tenant_id, company_id, scope_kind, id),
    INDEX ix_configuration_scope_type (tenant_id, company_id, product_type_id, id),
    INDEX ix_product_configuration_scope_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE product_configuration_scope")
