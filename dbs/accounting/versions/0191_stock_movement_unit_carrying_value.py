"""Retain the exact cost assigned to each physical unit; one atomic ALTER."""
from alembic import op
from sqlalchemy import text

revision = "0191"
down_revision = "0190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_movement_unit LIMIT 1")).first():
        raise RuntimeError("existing unit movements require reviewed cost backfill before migration")
    op.execute("""ALTER TABLE stock_movement_unit
        ADD COLUMN carrying_value NUMERIC(19,4) NOT NULL,
        ADD CONSTRAINT ck_stock_movement_unit_stock_movement_unit_value CHECK (carrying_value >= 0)""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_movement_unit LIMIT 1")).first():
        raise RuntimeError("retained per-unit stock cost requires a forward repair")
    op.execute("""ALTER TABLE stock_movement_unit
        DROP CHECK ck_stock_movement_unit_stock_movement_unit_value,
        DROP COLUMN carrying_value""")
