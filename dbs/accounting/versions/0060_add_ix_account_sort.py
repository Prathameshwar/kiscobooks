"""add ix account sort; one DDL statement per direction."""
from alembic import op

revision = '0060'
down_revision = '0059'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_account_sort ON account (tenant_id, company_id, sort_order, id)'
DOWNGRADE = 'DROP INDEX ix_account_sort ON account'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
