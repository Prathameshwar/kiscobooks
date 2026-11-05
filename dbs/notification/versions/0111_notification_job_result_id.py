"""Retain command result_id for safe replay. One DDL."""
from alembic import op
revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE notification_job ADD COLUMN result_id BINARY(16) NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE notification_job DROP COLUMN result_id")
