"""Add verified batch scope to native pricing; one atomic ALTER."""

import sqlalchemy as sa
from alembic import op

revision = "0221"
down_revision = "0220"
branch_labels = None
depends_on = None


_ALTER = """
ALTER TABLE item_price_scope
 ADD COLUMN lot_id BINARY(16) NULL,
 ADD COLUMN lot_key BINARY(16) GENERATED ALWAYS AS (COALESCE(lot_id, X'00000000000000000000000000000000')) STORED NOT NULL,
 ADD COLUMN lot_mrp NUMERIC(19,4) NULL,
 ADD COLUMN lot_currency VARCHAR(3) NULL,
 ADD COLUMN lot_unit_id BINARY(16) NULL,
 DROP INDEX uq_v86_1,
 ADD CONSTRAINT uq_v86_1 UNIQUE (tenant_id, company_id, item_id, lot_key),
 DROP CHECK ck_item_price_scope_v86_1,
 ADD CONSTRAINT ck_item_price_scope_v86_1 CHECK ((subject_kind = 'SKU' AND lot_id IS NULL) OR (subject_kind = 'LOT' AND lot_id IS NOT NULL)),
 ADD CONSTRAINT ck_item_price_scope_batch_mrp_shape CHECK ((lot_mrp IS NULL AND lot_currency IS NULL AND lot_unit_id IS NULL) OR (subject_kind = 'LOT' AND lot_mrp > 0 AND lot_currency IS NOT NULL AND lot_unit_id IS NOT NULL))
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    if op.get_context().as_sql or op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM item_price_scope WHERE lot_id IS NOT NULL")):
        raise RuntimeError("retain batch price scopes after use")
    op.execute("""
ALTER TABLE item_price_scope
 DROP INDEX uq_v86_1,
 ADD CONSTRAINT uq_v86_1 UNIQUE (tenant_id, company_id, item_id),
 DROP CHECK ck_item_price_scope_v86_1,
 DROP CHECK ck_item_price_scope_batch_mrp_shape,
 ADD CONSTRAINT ck_item_price_scope_v86_1 CHECK (subject_kind = 'SKU'),
 DROP COLUMN lot_key, DROP COLUMN lot_id, DROP COLUMN lot_mrp,
 DROP COLUMN lot_currency, DROP COLUMN lot_unit_id
""")
