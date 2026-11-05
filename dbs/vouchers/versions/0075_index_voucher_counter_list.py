"""Support counter-scoped voucher lists."""

from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_counter_list",
        "voucher_counter_context",
        ["tenant_id", "company_id", "counter_id", "revision_id"],
    )


def downgrade() -> None:
    # MySQL may reuse the list index to enforce the counter FK and drop its
    # original implicit supporting index. Replace it in the same DDL statement.
    op.execute("""
ALTER TABLE voucher_counter_context
    ADD INDEX ix_voucher_counter_fk_restore (tenant_id, company_id, counter_id),
    DROP INDEX ix_voucher_counter_list
""")
