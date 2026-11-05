"""add account rounding limit; one DDL statement per direction."""
from alembic import op

revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None

UPGRADE = 'ALTER TABLE account ADD COLUMN rounding_limit NUMERIC(19, 4)'
DOWNGRADE = 'ALTER TABLE account DROP COLUMN rounding_limit'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
