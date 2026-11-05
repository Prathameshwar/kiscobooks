"""add account group is deemed positive; one DDL statement per direction."""
from alembic import op

revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD COLUMN is_deemed_positive BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account_group DROP COLUMN is_deemed_positive'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
