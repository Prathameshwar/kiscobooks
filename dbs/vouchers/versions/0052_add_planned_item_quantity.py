"""Preserve non-posting requested quantity separately from actual/billed units."""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_item_detail "
        "ADD COLUMN planned_quantity NUMERIC(19,4) NULL, "
        "ADD CONSTRAINT ck_voucher_item_detail_planned_quantity "
        "CHECK (planned_quantity IS NULL OR planned_quantity >= 0)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_item_detail "
        "DROP CHECK ck_voucher_item_detail_planned_quantity, "
        "DROP COLUMN planned_quantity"
    )
