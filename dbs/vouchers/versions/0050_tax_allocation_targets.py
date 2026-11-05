"""Reuse common target membership for tax allocations; one atomic ALTER."""

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_charge_target "
        "DROP CHECK ck_voucher_charge_target_voucher_charge_target_purpose, "
        "ADD CONSTRAINT ck_voucher_charge_target_voucher_charge_target_purpose "
        "CHECK (purpose IN ('BASIS','STOCK_COST','TAX_BASE'))"
    )


def downgrade() -> None:
    # Requires tax target rows to be absent; never silently drops their history.
    op.execute(
        "ALTER TABLE voucher_charge_target "
        "DROP CHECK ck_voucher_charge_target_voucher_charge_target_purpose, "
        "ADD CONSTRAINT ck_voucher_charge_target_voucher_charge_target_purpose "
        "CHECK (purpose IN ('BASIS','STOCK_COST'))"
    )
