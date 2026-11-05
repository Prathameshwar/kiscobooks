"""Explicit historical-age provenance; NULL preserves legacy action-based inference."""

from alembic import op
from sqlalchemy import text

revision = "0216"
down_revision = "0215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stock_receipt_origin ADD COLUMN history_known BOOL NULL")


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            text("SELECT id FROM stock_receipt_origin WHERE history_known IS NOT NULL LIMIT 1")
        )
        .first()
    ):
        raise RuntimeError("receipt age provenance must be archived before downgrade")
    op.execute("ALTER TABLE stock_receipt_origin DROP COLUMN history_known")
