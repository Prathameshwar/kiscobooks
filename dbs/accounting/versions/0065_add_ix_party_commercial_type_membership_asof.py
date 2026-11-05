"""add ix party commercial type membership asof; one DDL statement per direction."""
from alembic import op

revision = '0065'
down_revision = '0064'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_party_commercial_type_membership_asof ON party_commercial_type_membership (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_party_commercial_type_membership_asof ON party_commercial_type_membership'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
