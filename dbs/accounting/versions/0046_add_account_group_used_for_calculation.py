"""add account group used for calculation; one DDL statement per direction."""
from alembic import op

revision = '0046'
down_revision = '0045'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN used_for_calculation BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN used_for_calculation'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
