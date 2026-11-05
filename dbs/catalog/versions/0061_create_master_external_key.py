"""Create master_external_key; one DDL paired with the mapping model."""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE master_external_key (
    source_namespace VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    external_key VARCHAR(200) COLLATE utf8mb4_bin NOT NULL,
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
    CONSTRAINT ck_master_external_key_master_external_key_entity CHECK (entity_type IN
        ('catalog.unit_of_measure', 'catalog.pack_type', 'catalog.item_group',
        'catalog.category_scheme', 'catalog.item_category', 'catalog.product_type',
        'catalog.brand', 'catalog.brand_series', 'catalog.manufacturer',
        'catalog.manufacturer_site', 'catalog.attribute_definition', 'catalog.attribute_option',
        'catalog.attribute_set', 'catalog.identifier_profile',
        'catalog.inventory_profile_template', 'catalog.warranty_policy', 'catalog.return_policy',
        'catalog.handling_profile')),
    CONSTRAINT ck_master_external_key_master_external_key_lengths CHECK
        (source_namespace <> '' AND external_key <> ''),
    CONSTRAINT ck_master_external_key_master_external_key_version CHECK (row_version >= 1),
    CONSTRAINT pk_master_external_key PRIMARY KEY (id),
    CONSTRAINT uq_master_external_key_identity UNIQUE (tenant_id, company_id, entity_type,
        source_namespace, external_key),
    CONSTRAINT uq_master_external_key_scope UNIQUE (tenant_id, company_id, id),
    KEY ix_master_external_key_active (tenant_id, company_id, entity_type, target_id, is_active,
        id),
    KEY ix_master_external_key_owner (tenant_id, company_id, entity_type, target_id, id),
    KEY ix_master_external_key_source (tenant_id, company_id, entity_type, target_id,
        source_namespace, id),
    KEY ix_master_external_key_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE master_external_key")
