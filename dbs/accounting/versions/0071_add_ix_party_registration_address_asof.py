"""add ix party registration address asof; one DDL statement per direction."""
from alembic import op

revision = '0071'
down_revision = '0070'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_party_registration_address_asof ON party_registration_address (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_party_registration_address_asof ON party_registration_address'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
