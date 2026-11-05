"""add ix party identifier asof; one DDL statement per direction."""
from alembic import op

revision = '0067'
down_revision = '0066'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_party_identifier_asof ON party_identifier (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_party_identifier_asof ON party_identifier'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
