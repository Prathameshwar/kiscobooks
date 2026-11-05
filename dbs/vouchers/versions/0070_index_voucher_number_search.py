"""Support indexed voucher display-number prefix and exact search."""

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_number_search",
        "voucher_number_assignment",
        ["tenant_id", "company_id", "display_number", "revision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voucher_number_search", table_name="voucher_number_assignment")
