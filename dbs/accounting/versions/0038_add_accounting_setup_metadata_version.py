"""add accounting setup metadata version; one DDL statement per direction."""
from alembic import op

revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE accounting_setup ADD COLUMN metadata_version INTEGER NOT NULL DEFAULT '0'"
DOWNGRADE = 'ALTER TABLE accounting_setup DROP COLUMN metadata_version'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
