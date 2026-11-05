"""add account sort order; one DDL statement per direction."""
from alembic import op

revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account ADD COLUMN sort_order INTEGER NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account DROP COLUMN sort_order'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
