"""Support current-revision voucher lists by party."""

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_party_list",
        "voucher_party",
        ["tenant_id", "company_id", "party_id", "revision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voucher_party_list", table_name="voucher_party")
