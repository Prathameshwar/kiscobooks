"""Support company/type-scoped voucher keyset lists."""

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_type_list", "voucher", ["tenant_id", "company_id", "type_id", "id"]
    )


def downgrade() -> None:
    # Preserve an index for the voucher-type FK when MySQL reused the list index.
    op.execute("""
ALTER TABLE voucher
    ADD INDEX ix_voucher_type_fk_restore (tenant_id, company_id, type_id),
    DROP INDEX ix_voucher_type_list
""")
