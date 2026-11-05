"""add account group is reserved; one DDL statement per direction."""
from alembic import op

revision = '0040'
down_revision = '0039'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN is_reserved BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN is_reserved'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
