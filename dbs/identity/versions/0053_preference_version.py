"""Versioned preference projection. One atomic DDL per direction."""
from alembic import op
revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""ALTER TABLE user_notification_preference
        ADD COLUMN source_version BIGINT NOT NULL DEFAULT 1""")

def downgrade() -> None:
    op.execute("ALTER TABLE user_notification_preference DROP COLUMN source_version")
