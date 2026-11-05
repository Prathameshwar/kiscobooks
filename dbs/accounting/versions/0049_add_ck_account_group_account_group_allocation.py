"""add ck account group account group allocation; one DDL statement per direction."""
from alembic import op

revision = '0049'
down_revision = '0048'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_group ADD CONSTRAINT ck_account_group_account_group_allocation CHECK (allocation_method IN ('NOT_APPLICABLE', 'BY_QTY', 'BY_VALUE'))"
DOWNGRADE = 'ALTER TABLE account_group DROP CHECK ck_account_group_account_group_allocation'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
