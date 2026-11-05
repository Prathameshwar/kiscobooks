"""Track configuration job claims. One DDL statement."""
from alembic import op
revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE notification_job ADD COLUMN started_at DATETIME(6) NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE notification_job DROP COLUMN started_at")
