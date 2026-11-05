"""add ix party credit policy asof; one DDL statement per direction."""
from alembic import op

revision = '0066'
down_revision = '0065'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_party_credit_policy_asof ON party_credit_policy (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_party_credit_policy_asof ON party_credit_policy'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
