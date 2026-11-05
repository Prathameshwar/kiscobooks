"""add account group allocation method; one DDL statement per direction."""
from alembic import op

revision = '0047'
down_revision = '0046'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN allocation_method VARCHAR(30) NOT NULL DEFAULT 'NOT_APPLICABLE'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN allocation_method'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
