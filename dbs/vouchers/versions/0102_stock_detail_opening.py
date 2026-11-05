"""Typed immutable opening capture on its existing stock revision child; one ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_stock_detail ADD COLUMN opening JSON NULL")


def downgrade() -> None:
    if op.get_bind().execute(text(
        "SELECT id FROM voucher_stock_detail WHERE opening IS NOT NULL LIMIT 1"
    )).first():
        raise RuntimeError("retained opening capture requires a reviewed archive before downgrade")
    op.execute("ALTER TABLE voucher_stock_detail DROP COLUMN opening")
