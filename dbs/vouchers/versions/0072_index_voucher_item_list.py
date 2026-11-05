"""Support current-revision voucher lists by item."""

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_item_list",
        "voucher_item_detail",
        ["tenant_id", "company_id", "item_id", "revision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voucher_item_list", table_name="voucher_item_detail")
