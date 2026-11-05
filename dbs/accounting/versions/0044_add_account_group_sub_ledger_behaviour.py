"""add account group sub ledger behaviour; one DDL statement per direction."""
from alembic import op

revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN sub_ledger_behaviour BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN sub_ledger_behaviour'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
