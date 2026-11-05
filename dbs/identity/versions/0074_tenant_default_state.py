"""Persist an optional tenant state without changing existing tenants."""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenant ADD COLUMN default_state_code VARCHAR(6) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE tenant DROP COLUMN default_state_code")
