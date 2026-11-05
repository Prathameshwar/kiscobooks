"""add account tax profile duty type; one DDL statement per direction."""
from alembic import op

revision = '0062'
down_revision = '0061'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_tax_profile ADD COLUMN duty_type VARCHAR(20) NOT NULL DEFAULT 'OTHER'"
DOWNGRADE = 'ALTER TABLE account_tax_profile DROP COLUMN duty_type'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
