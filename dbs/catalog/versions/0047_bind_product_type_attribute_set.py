"""Bind product-type requirements to real attribute template revisions; one ALTER."""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_ALTER = """
ALTER TABLE product_type_revision
    ADD COLUMN attribute_set_revision_id BINARY(16) NULL,
    ADD CONSTRAINT fk_product_type_revision_attribute_set FOREIGN KEY (tenant_id, company_id,
        attribute_set_revision_id) REFERENCES attribute_set_revision (tenant_id, company_id, id),
    ADD INDEX ix_product_type_revision_attribute_set (tenant_id, company_id,
        attribute_set_revision_id)
"""
_REVERT = """
ALTER TABLE product_type_revision
    DROP FOREIGN KEY fk_product_type_revision_attribute_set,
    DROP INDEX ix_product_type_revision_attribute_set,
    DROP COLUMN attribute_set_revision_id
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(_REVERT)
