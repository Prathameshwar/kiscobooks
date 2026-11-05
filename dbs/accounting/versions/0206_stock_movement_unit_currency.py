"""Explicit carrying-value currency for stock_movement_unit; one atomic ALTER.

Existing physical data requires a reviewed lineage-aware backfill first.
No default can silently relabel retained monetary evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0206"
down_revision = "0205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_movement_unit LIMIT 1")):
        raise RuntimeError("Retained stock values require a reviewed currency backfill")
    op.execute("ALTER TABLE stock_movement_unit ADD COLUMN currency VARCHAR(3) NOT NULL")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_movement_unit LIMIT 1")):
        raise RuntimeError("Retained stock currency evidence prevents downgrade")
    op.execute("ALTER TABLE stock_movement_unit DROP COLUMN currency")
