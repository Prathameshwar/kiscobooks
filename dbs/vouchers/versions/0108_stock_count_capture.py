"""Retain the native count observation reference; one atomic ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_stock_detail ADD COLUMN count JSON NULL")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM voucher_stock_detail WHERE count IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("archive retained count capture before downgrade")
    op.execute("ALTER TABLE voucher_stock_detail DROP COLUMN count")
