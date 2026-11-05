"""add account group is revenue; one DDL statement per direction."""
from alembic import op

revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN is_revenue BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN is_revenue'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
