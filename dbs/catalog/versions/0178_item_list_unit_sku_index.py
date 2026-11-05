"""Index base-unit-filtered item SKU pages; one DDL statement."""

from alembic import op

revision = "0178"
down_revision = "0177"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE item ADD INDEX ix_item_unit_sku (tenant_id, company_id, base_unit_id, sku, id)"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE item DROP INDEX ix_item_unit_sku")
