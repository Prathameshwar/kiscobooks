"""Optional independent tax allocation basis; one atomic ALTER per direction."""

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_charge_detail ADD COLUMN tax_allocation_basis VARCHAR(10) NULL")


def downgrade() -> None:
    # Destructive schema rollback; accepted revision payloads remain immutable.
    op.execute("ALTER TABLE voucher_charge_detail DROP COLUMN tax_allocation_basis")
