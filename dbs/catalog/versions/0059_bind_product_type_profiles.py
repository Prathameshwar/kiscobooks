"""Bind product types to actual native profile revisions; one atomic ALTER."""

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

_ALTER = """
ALTER TABLE product_type_revision
    ADD COLUMN inventory_template_revision_id BINARY(16) NULL,
    ADD CONSTRAINT fk_product_type_revision_inventory FOREIGN KEY (tenant_id, company_id,
        inventory_template_revision_id) REFERENCES inventory_profile_template_revision
        (tenant_id, company_id, id),
    ADD INDEX ix_product_type_revision_inventory
        (tenant_id, company_id, inventory_template_revision_id),
    ADD COLUMN warranty_revision_id BINARY(16) NULL,
    ADD CONSTRAINT fk_product_type_revision_warranty FOREIGN KEY (tenant_id, company_id,
        warranty_revision_id) REFERENCES warranty_policy_revision (tenant_id, company_id, id),
    ADD INDEX ix_product_type_revision_warranty (tenant_id, company_id, warranty_revision_id),
    ADD COLUMN return_policy_revision_id BINARY(16) NULL,
    ADD CONSTRAINT fk_product_type_revision_return FOREIGN KEY (tenant_id, company_id,
        return_policy_revision_id) REFERENCES return_policy_revision (tenant_id, company_id, id),
    ADD INDEX ix_product_type_revision_return (tenant_id, company_id, return_policy_revision_id),
    ADD COLUMN handling_revision_id BINARY(16) NULL,
    ADD CONSTRAINT fk_product_type_revision_handling FOREIGN KEY (tenant_id, company_id,
        handling_revision_id) REFERENCES handling_profile_revision (tenant_id, company_id, id),
    ADD INDEX ix_product_type_revision_handling (tenant_id, company_id, handling_revision_id)
"""
_REVERT = """
ALTER TABLE product_type_revision
    DROP FOREIGN KEY fk_product_type_revision_inventory,
    DROP INDEX ix_product_type_revision_inventory,
    DROP COLUMN inventory_template_revision_id,
    DROP FOREIGN KEY fk_product_type_revision_warranty,
    DROP INDEX ix_product_type_revision_warranty,
    DROP COLUMN warranty_revision_id,
    DROP FOREIGN KEY fk_product_type_revision_return,
    DROP INDEX ix_product_type_revision_return,
    DROP COLUMN return_policy_revision_id,
    DROP FOREIGN KEY fk_product_type_revision_handling,
    DROP INDEX ix_product_type_revision_handling,
    DROP COLUMN handling_revision_id
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(_REVERT)
