"""Retain a native-signature-bound attempt reference for ambiguous-send recovery."""
from alembic import op

revision = "0115"
down_revision = "0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE provider_event ADD COLUMN attempt_key VARCHAR(80) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE provider_event DROP COLUMN attempt_key")
