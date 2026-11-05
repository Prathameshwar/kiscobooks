"""Retain a batch's immutable initial physical MRP; one atomic ALTER."""

import sqlalchemy as sa
from alembic import op

revision = "0235"
down_revision = "0234"
branch_labels = None
depends_on = None


_ALTER = """
ALTER TABLE stock_lot
 ADD COLUMN mrp_amount NUMERIC(19,4) NULL,
 ADD COLUMN mrp_currency VARCHAR(3) NULL,
 ADD COLUMN mrp_unit_id BINARY(16) NULL,
 ADD CONSTRAINT ck_stock_lot_stock_lot_mrp CHECK ((mrp_amount IS NULL AND mrp_currency IS NULL AND mrp_unit_id IS NULL) OR (mrp_amount > 0 AND mrp_currency IS NOT NULL AND mrp_unit_id IS NOT NULL))
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    if op.get_context().as_sql or op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM stock_lot WHERE mrp_amount IS NOT NULL")):
        raise RuntimeError("retain physical MRP declarations after use")
    op.execute("ALTER TABLE stock_lot DROP CHECK ck_stock_lot_stock_lot_mrp, DROP COLUMN mrp_amount, DROP COLUMN mrp_currency, DROP COLUMN mrp_unit_id")
