"""Explicit carrying-value currency for stock_source_claim; one atomic ALTER.

Existing physical data requires a reviewed lineage-aware backfill first.
No default can silently relabel retained monetary evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0207"
down_revision = "0206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_source_claim LIMIT 1")):
        raise RuntimeError("Retained stock values require a reviewed currency backfill")
    op.execute("ALTER TABLE stock_source_claim ADD COLUMN currency VARCHAR(3) NOT NULL")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_source_claim LIMIT 1")):
        raise RuntimeError("Retained stock currency evidence prevents downgrade")
    op.execute("ALTER TABLE stock_source_claim DROP COLUMN currency")
