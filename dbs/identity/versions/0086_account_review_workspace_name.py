"""Preserve the requested workspace name on platform account reviews."""

from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE account_review ADD COLUMN workspace_name VARCHAR(200) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE account_review DROP COLUMN workspace_name")
