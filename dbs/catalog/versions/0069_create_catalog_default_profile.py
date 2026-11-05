"""Create catalog_default_profile; one atomic DDL with a reversible downgrade."""

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_default_profile (
    goods_type_revision_mode VARCHAR(10) NOT NULL,
    goods_type_revision_id BINARY(16) NULL,
    service_type_revision_mode VARCHAR(10) NOT NULL,
    service_type_revision_id BINARY(16) NULL,
    inventory_template_revision_mode VARCHAR(10) NOT NULL,
    inventory_template_revision_id BINARY(16) NULL,
    warranty_revision_mode VARCHAR(10) NOT NULL,
    warranty_revision_id BINARY(16) NULL,
    return_policy_revision_mode VARCHAR(10) NOT NULL,
    return_policy_revision_id BINARY(16) NULL,
    handling_revision_mode VARCHAR(10) NOT NULL,
    handling_revision_id BINARY(16) NULL,
    identifier_profile_mode VARCHAR(10) NOT NULL,
    identifier_profile_id BINARY(16) NULL,
    draft_id BINARY(16) NULL,
    revision_id BINARY(16) NULL,
    company_id BINARY(16) NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_catalog_default_profile PRIMARY KEY (id),
    CONSTRAINT uq_catalog_default_profile_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_catalog_default_profile_draft UNIQUE (tenant_id, company_id, draft_id),
    CONSTRAINT uq_catalog_default_profile_revision UNIQUE (tenant_id, company_id, revision_id),
    CONSTRAINT fk_catalog_default_profile_draft FOREIGN KEY(tenant_id, company_id, draft_id)
        REFERENCES product_configuration_draft (tenant_id, company_id, id),
    CONSTRAINT fk_catalog_default_profile_revision FOREIGN KEY(tenant_id, company_id,
        revision_id) REFERENCES product_configuration_revision (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_catalog_default_profile_owner CHECK ((draft_id IS
        NULL) <> (revision_id IS NULL)),
    CONSTRAINT fk_default_goods_type_revision FOREIGN KEY(tenant_id, company_id,
        goods_type_revision_id) REFERENCES product_type_revision (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_default_goods_type_revision_mode CHECK
        (goods_type_revision_mode IN ('INHERIT','CLEAR','VALUE') AND ((goods_type_revision_mode
        = 'VALUE' AND goods_type_revision_id IS NOT NULL) OR (goods_type_revision_mode <>
        'VALUE' AND goods_type_revision_id IS NULL))),
    CONSTRAINT fk_default_service_type_revision FOREIGN KEY(tenant_id, company_id,
        service_type_revision_id) REFERENCES product_type_revision (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_default_service_type_revision_mode CHECK
        (service_type_revision_mode IN ('INHERIT','CLEAR','VALUE') AND
        ((service_type_revision_mode = 'VALUE' AND service_type_revision_id IS NOT NULL) OR
        (service_type_revision_mode <> 'VALUE' AND service_type_revision_id IS NULL))),
    CONSTRAINT fk_default_inventory_template_revision FOREIGN KEY(tenant_id, company_id,
        inventory_template_revision_id) REFERENCES inventory_profile_template_revision
        (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_default_inventory_template_re_d847 CHECK
        (inventory_template_revision_mode IN ('INHERIT','CLEAR','VALUE') AND
        ((inventory_template_revision_mode = 'VALUE' AND inventory_template_revision_id IS NOT
        NULL) OR (inventory_template_revision_mode <> 'VALUE' AND inventory_template_revision_id
        IS NULL))),
    CONSTRAINT fk_default_warranty_revision FOREIGN KEY(tenant_id, company_id,
        warranty_revision_id) REFERENCES warranty_policy_revision (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_default_warranty_revision_mode CHECK
        (warranty_revision_mode IN ('INHERIT','CLEAR','VALUE') AND ((warranty_revision_mode =
        'VALUE' AND warranty_revision_id IS NOT NULL) OR (warranty_revision_mode <> 'VALUE' AND
        warranty_revision_id IS NULL))),
    CONSTRAINT fk_default_return_policy_revision FOREIGN KEY(tenant_id, company_id,
        return_policy_revision_id) REFERENCES return_policy_revision (tenant_id, company_id,
        id),
    CONSTRAINT ck_catalog_default_profile_default_return_policy_revision_mode CHECK
        (return_policy_revision_mode IN ('INHERIT','CLEAR','VALUE') AND
        ((return_policy_revision_mode = 'VALUE' AND return_policy_revision_id IS NOT NULL) OR
        (return_policy_revision_mode <> 'VALUE' AND return_policy_revision_id IS NULL))),
    CONSTRAINT fk_default_handling_revision FOREIGN KEY(tenant_id, company_id,
        handling_revision_id) REFERENCES handling_profile_revision (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_default_handling_revision_mode CHECK
        (handling_revision_mode IN ('INHERIT','CLEAR','VALUE') AND ((handling_revision_mode =
        'VALUE' AND handling_revision_id IS NOT NULL) OR (handling_revision_mode <> 'VALUE' AND
        handling_revision_id IS NULL))),
    CONSTRAINT fk_default_identifier_profile FOREIGN KEY(tenant_id, company_id,
        identifier_profile_id) REFERENCES identifier_profile (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_default_profile_default_identifier_profile_mode CHECK
        (identifier_profile_mode IN ('INHERIT','CLEAR','VALUE') AND ((identifier_profile_mode =
        'VALUE' AND identifier_profile_id IS NOT NULL) OR (identifier_profile_mode <> 'VALUE'
        AND identifier_profile_id IS NULL))),
    INDEX ix_catalog_default_profile_tenant_id (tenant_id),
    INDEX ix_default_goods_type_revision (tenant_id, company_id, goods_type_revision_id, id),
    INDEX ix_default_handling_revision (tenant_id, company_id, handling_revision_id, id),
    INDEX ix_default_identifier_profile (tenant_id, company_id, identifier_profile_id, id),
    INDEX ix_default_inventory_template_revision (tenant_id, company_id,
        inventory_template_revision_id, id),
    INDEX ix_default_return_policy_revision (tenant_id, company_id, return_policy_revision_id, id),
    INDEX ix_default_service_type_revision (tenant_id, company_id, service_type_revision_id, id),
    INDEX ix_default_warranty_revision (tenant_id, company_id, warranty_revision_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_default_profile")
