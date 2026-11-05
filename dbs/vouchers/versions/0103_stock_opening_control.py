"""Pin the opaque Accounting cutover reference on the immutable revision; one ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_stock_context ADD COLUMN opening_control_id BINARY(16) NULL")


def downgrade() -> None:
    if op.get_bind().execute(text(
        "SELECT id FROM voucher_stock_context WHERE opening_control_id IS NOT NULL LIMIT 1"
    )).first():
        raise RuntimeError("archive retained cutover references before downgrade")
    op.execute("ALTER TABLE voucher_stock_context DROP COLUMN opening_control_id")
