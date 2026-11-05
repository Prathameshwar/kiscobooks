"""add ix account group sort; one DDL statement per direction."""
from alembic import op

revision = '0051'
down_revision = '0050'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_account_group_sort ON account_group (tenant_id, company_id, sort_order, id)'
DOWNGRADE = 'DROP INDEX ix_account_group_sort ON account_group'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
