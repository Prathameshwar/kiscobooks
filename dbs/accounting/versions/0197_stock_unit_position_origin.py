"""Retain each unit's physical cohort; one atomic ALTER after an empty-legacy guard."""
from alembic import op
from sqlalchemy import text

revision = "0197"
down_revision = "0196"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_unit_position LIMIT 1")).first():
        raise RuntimeError("existing unit custody needs reviewed physical-origin backfill")
    op.execute("""ALTER TABLE stock_unit_position
        ADD COLUMN origin_id BINARY(16) NULL,
        ADD CONSTRAINT fk_stock_unit_position_origin FOREIGN KEY (tenant_id, company_id, origin_id) REFERENCES stock_receipt_origin (tenant_id, company_id, id),
        ADD INDEX ix_stock_unit_position_origin_id (tenant_id, company_id, origin_id),
        ADD CONSTRAINT ck_stock_unit_position_stock_unit_position_origin CHECK (position_id IS NULL OR origin_id IS NOT NULL)""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_unit_position LIMIT 1")).first():
        raise RuntimeError("retained unit custody needs a forward repair")
    op.execute("""ALTER TABLE stock_unit_position
        DROP FOREIGN KEY fk_stock_unit_position_origin,
        DROP INDEX ix_stock_unit_position_origin_id,
        DROP CHECK ck_stock_unit_position_stock_unit_position_origin,
        DROP COLUMN origin_id""")
