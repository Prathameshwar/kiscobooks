"""B24: a purchased goods line may record that its GST cannot be claimed."""

from alembic import op
from sqlalchemy import text

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_supply_detail ADD COLUMN input_credit VARCHAR(10) NULL")


def downgrade() -> None:
    if op.get_bind().execute(
        text("SELECT id FROM voucher_supply_detail WHERE input_credit IS NOT NULL LIMIT 1")
    ).first():
        raise RuntimeError("archive retained input-credit evidence before downgrade")
    op.execute("ALTER TABLE voucher_supply_detail DROP COLUMN input_credit")
