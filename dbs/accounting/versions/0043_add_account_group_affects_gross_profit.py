"""add account group affects gross profit; one DDL statement per direction."""
from alembic import op

revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN affects_gross_profit BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN affects_gross_profit'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
