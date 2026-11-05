"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_import_row ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0'
DOWN = 'ALTER TABLE voucher_import_row DROP COLUMN error_count'

def upgrade() -> None:
    op.execute(UP)
    op.execute("UPDATE voucher_import_row SET error_count = JSON_LENGTH(errors)")

def downgrade() -> None:
    op.execute(DOWN)
