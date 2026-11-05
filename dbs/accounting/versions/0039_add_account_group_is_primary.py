"""add account group is primary; one DDL statement per direction."""
from alembic import op

revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN is_primary BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN is_primary'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
