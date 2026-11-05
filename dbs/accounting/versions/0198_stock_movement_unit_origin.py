"""Immutable unit membership keeps physical age/source identity; one atomic ALTER."""
from alembic import op
from sqlalchemy import text

revision = "0198"
down_revision = "0197"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_movement_unit LIMIT 1")).first():
        raise RuntimeError("existing unit movement history needs reviewed physical-origin backfill")
    op.execute("""ALTER TABLE stock_movement_unit
        ADD COLUMN origin_id BINARY(16) NOT NULL,
        ADD CONSTRAINT fk_stock_movement_unit_origin FOREIGN KEY (tenant_id, company_id, origin_id) REFERENCES stock_receipt_origin (tenant_id, company_id, id),
        ADD INDEX ix_stock_movement_unit_origin_id (tenant_id, company_id, origin_id)""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_movement_unit LIMIT 1")).first():
        raise RuntimeError("retained physical origin evidence needs a forward repair")
    op.execute("""ALTER TABLE stock_movement_unit
        DROP FOREIGN KEY fk_stock_movement_unit_origin,
        DROP INDEX ix_stock_movement_unit_origin_id,
        DROP COLUMN origin_id""")
