"""Create master_alias; one DDL paired with the mapping model."""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE master_alias (
    alias VARCHAR(100) NOT NULL,
    canonical_value VARCHAR(200) COLLATE utf8mb4_bin NOT NULL,
    normalization_version INTEGER NOT NULL,
    company_id BINARY(16) NOT NULL,
    entity_type VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    target_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT ck_master_alias_master_alias_entity CHECK (entity_type IN
        ('catalog.unit_of_measure', 'catalog.pack_type', 'catalog.item_group',
        'catalog.category_scheme', 'catalog.item_category', 'catalog.product_type',
        'catalog.brand', 'catalog.brand_series', 'catalog.manufacturer',
        'catalog.manufacturer_site', 'catalog.attribute_definition', 'catalog.attribute_option',
        'catalog.attribute_set', 'catalog.identifier_profile',
        'catalog.inventory_profile_template', 'catalog.warranty_policy', 'catalog.return_policy',
        'catalog.handling_profile')),
    CONSTRAINT ck_master_alias_master_alias_lengths CHECK (alias <> '' AND canonical_value <> ''),
    CONSTRAINT ck_master_alias_master_alias_versions CHECK (row_version >= 1 AND
        normalization_version = 1),
    CONSTRAINT pk_master_alias PRIMARY KEY (id),
    CONSTRAINT uq_master_alias_identity UNIQUE (tenant_id, company_id, entity_type,
        canonical_value),
    CONSTRAINT uq_master_alias_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_master_alias_active (tenant_id, company_id, entity_type, target_id, is_active,
        canonical_value, id),
    KEY ix_master_alias_owner (tenant_id, company_id, entity_type, target_id, canonical_value,
        id),
    KEY ix_master_alias_owner_id (tenant_id, company_id, entity_type, target_id, id),
    KEY ix_master_alias_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE master_alias")
