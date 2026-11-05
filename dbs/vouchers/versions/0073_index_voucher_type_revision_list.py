"""Support lists filtered by current voucher type revision."""

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_revision_type_list",
        "voucher_revision",
        ["tenant_id", "company_id", "type_revision_id", "voucher_id", "revision_number"],
    )


def downgrade() -> None:
    # Preserve an index for the type-revision FK when MySQL reused the list index.
    op.execute("""
ALTER TABLE voucher_revision
    ADD INDEX ix_voucher_revision_type_fk_restore (tenant_id, company_id, type_revision_id),
    DROP INDEX ix_voucher_revision_type_list
""")
