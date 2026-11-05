"""Explicit carrying-value currency for stock_cost_layer; one atomic ALTER.

Existing physical data requires a reviewed lineage-aware backfill first.
No default can silently relabel retained monetary evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0202"
down_revision = "0201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_cost_layer LIMIT 1")):
        raise RuntimeError("Retained stock values require a reviewed currency backfill")
    op.execute("ALTER TABLE stock_cost_layer ADD COLUMN currency VARCHAR(3) NOT NULL")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_cost_layer LIMIT 1")):
        raise RuntimeError("Retained stock currency evidence prevents downgrade")
    op.execute("ALTER TABLE stock_cost_layer DROP COLUMN currency")
