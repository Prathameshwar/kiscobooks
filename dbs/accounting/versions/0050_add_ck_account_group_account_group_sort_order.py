"""add ck account group account group sort order; one DDL statement per direction."""
from alembic import op

revision = '0050'
down_revision = '0049'
branch_labels = None
depends_on = None

UPGRADE = 'ALTER TABLE account_group ADD CONSTRAINT ck_account_group_account_group_sort_order CHECK (sort_order >= 0 AND sort_order <= 1000000)'
DOWNGRADE = 'ALTER TABLE account_group DROP CHECK ck_account_group_account_group_sort_order'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
