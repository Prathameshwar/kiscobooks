"""Index status-filtered item SKU pages; one DDL statement."""

from alembic import op

revision = "0177"
down_revision = "0176"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE item ADD INDEX ix_item_status (tenant_id, company_id, status, sku, id)"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE item DROP INDEX ix_item_status")
