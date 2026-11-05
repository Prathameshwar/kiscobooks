"""add ix party accounting policy asof; one DDL statement per direction."""
from alembic import op

revision = '0064'
down_revision = '0063'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_party_accounting_policy_asof ON party_accounting_policy (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_party_accounting_policy_asof ON party_accounting_policy'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
