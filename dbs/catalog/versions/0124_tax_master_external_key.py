"""Register tax masters for scoped metadata mappings.

Downgrade rejects existing tax mappings; it never deletes retained mapping evidence.
"""
from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE master_external_key DROP CHECK ck_master_external_key_master_external_key_entity, ADD CONSTRAINT ck_master_external_key_master_external_key_entity CHECK (entity_type IN ('catalog.unit_of_measure', 'catalog.pack_type', 'catalog.item_group', 'catalog.category_scheme', 'catalog.item_category', 'catalog.product_type', 'catalog.brand', 'catalog.brand_series', 'catalog.manufacturer', 'catalog.manufacturer_site', 'catalog.attribute_definition', 'catalog.attribute_option', 'catalog.attribute_set', 'catalog.identifier_profile', 'catalog.inventory_profile_template', 'catalog.warranty_policy', 'catalog.return_policy', 'catalog.handling_profile', 'catalog.tax_category', 'catalog.tax_rule', 'catalog.tax_classification'))"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE master_external_key DROP CHECK ck_master_external_key_master_external_key_entity, ADD CONSTRAINT ck_master_external_key_master_external_key_entity CHECK (entity_type IN ('catalog.unit_of_measure', 'catalog.pack_type', 'catalog.item_group', 'catalog.category_scheme', 'catalog.item_category', 'catalog.product_type', 'catalog.brand', 'catalog.brand_series', 'catalog.manufacturer', 'catalog.manufacturer_site', 'catalog.attribute_definition', 'catalog.attribute_option', 'catalog.attribute_set', 'catalog.identifier_profile', 'catalog.inventory_profile_template', 'catalog.warranty_policy', 'catalog.return_policy', 'catalog.handling_profile'))")
