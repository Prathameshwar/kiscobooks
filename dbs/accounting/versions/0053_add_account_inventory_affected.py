"""add account inventory affected; one DDL statement per direction."""
from alembic import op

revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account ADD COLUMN inventory_affected BOOL NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE account DROP COLUMN inventory_affected'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
