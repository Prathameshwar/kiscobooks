"""Retain command request_hash for safe replay. One DDL."""
from alembic import op
revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE notification_job ADD COLUMN request_hash BINARY(32) NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE notification_job DROP COLUMN request_hash")
