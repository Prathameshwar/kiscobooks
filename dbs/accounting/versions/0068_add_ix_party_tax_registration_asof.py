"""add ix party tax registration asof; one DDL statement per direction."""
from alembic import op

revision = '0068'
down_revision = '0067'
branch_labels = None
depends_on = None

UPGRADE = 'CREATE INDEX ix_party_tax_registration_asof ON party_tax_registration (tenant_id, company_id, valid_from, id)'
DOWNGRADE = 'DROP INDEX ix_party_tax_registration_asof ON party_tax_registration'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
