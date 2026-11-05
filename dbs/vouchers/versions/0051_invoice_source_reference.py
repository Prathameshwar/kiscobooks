"""Optional original invoice reference on common invoice detail; one atomic ALTER."""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_invoice_detail ADD COLUMN source_invoice_id BINARY(16) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE voucher_invoice_detail DROP COLUMN source_invoice_id")
