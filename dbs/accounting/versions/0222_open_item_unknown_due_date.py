"""Preserve unknown on-account due_date; one atomic ALTER."""
from alembic import op
from sqlalchemy import text
revision = "0222"
down_revision = "0221"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE open_item MODIFY COLUMN due_date DATE NULL")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM open_item WHERE due_date IS NULL LIMIT 1")).first():
        raise RuntimeError("unknown-date opening evidence cannot be replaced by invented dates")
    op.execute("ALTER TABLE open_item MODIFY COLUMN due_date DATE NOT NULL")
