"""Support voucher date range and keyset ordering from current revisions."""

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_revision_date_list",
        "voucher_revision",
        ["tenant_id", "company_id", "document_date", "voucher_id", "revision_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_voucher_revision_date_list", table_name="voucher_revision")
