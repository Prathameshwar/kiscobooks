"""add ix account posting mapping asof; one DDL statement per direction."""
from alembic import op

revision = '0072'
down_revision = '0071'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_account_posting_mapping_asof ON account_posting_mapping (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_account_posting_mapping_asof ON account_posting_mapping'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
