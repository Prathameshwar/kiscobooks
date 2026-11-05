"""Preserve unknown on-account document_date; one atomic ALTER."""
from alembic import op
from sqlalchemy import text
revision = "0221"
down_revision = "0220"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE open_item MODIFY COLUMN document_date DATE NULL")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM open_item WHERE document_date IS NULL LIMIT 1")).first():
        raise RuntimeError("unknown-date opening evidence cannot be replaced by invented dates")
    op.execute("ALTER TABLE open_item MODIFY COLUMN document_date DATE NOT NULL")
