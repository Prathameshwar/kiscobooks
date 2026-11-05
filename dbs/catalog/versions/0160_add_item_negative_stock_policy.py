"""Add item-level negative-stock policy in one DDL revision."""

from alembic import op

revision = "0160"
down_revision = "0159"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE item_inventory_profile "
    "ADD COLUMN negative_stock_policy VARCHAR(10) NOT NULL DEFAULT 'BLOCK', "
    "ADD CONSTRAINT ck_item_inventory_profile_negative_stock "
    "CHECK (negative_stock_policy IN ('BLOCK','WARN','ALLOW'))"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE item_inventory_profile "
        "DROP CHECK ck_item_inventory_profile_negative_stock, "
        "DROP COLUMN negative_stock_policy"
    )
