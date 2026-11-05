"""add account rounding method; one DDL statement per direction."""
from alembic import op

revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account ADD COLUMN rounding_method VARCHAR(20) NOT NULL DEFAULT 'NONE'"
DOWNGRADE = 'ALTER TABLE account DROP COLUMN rounding_method'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
