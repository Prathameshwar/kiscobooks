"""Support role/principal voucher lists without a revision-wide scan."""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_assignment_principal_list",
        "voucher_assignment",
        ["tenant_id", "company_id", "role", "principal_id", "revision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voucher_assignment_principal_list", table_name="voucher_assignment")
