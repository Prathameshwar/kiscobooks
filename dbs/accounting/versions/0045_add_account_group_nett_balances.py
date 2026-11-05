"""add account group nett balances; one DDL statement per direction."""
from alembic import op

revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN nett_balances BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN nett_balances'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
