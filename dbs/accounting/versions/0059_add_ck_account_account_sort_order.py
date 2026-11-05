"""add ck account account sort order; one DDL statement per direction."""
from alembic import op

revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None

UPGRADE = 'ALTER TABLE account ADD CONSTRAINT ck_account_account_sort_order CHECK (sort_order >= 0 AND sort_order <= 1000000)'
DOWNGRADE = 'ALTER TABLE account DROP CHECK ck_account_account_sort_order'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
