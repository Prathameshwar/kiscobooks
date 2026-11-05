"""Retain entered/actual measured stock evidence; one ALTER statement."""

from alembic import op
from sqlalchemy import text

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_stock_detail ADD COLUMN quantity_entry JSON NULL")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM voucher_stock_detail WHERE quantity_entry IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("archive entered stock quantity evidence before downgrade")
    op.execute("ALTER TABLE voucher_stock_detail DROP COLUMN quantity_entry")
