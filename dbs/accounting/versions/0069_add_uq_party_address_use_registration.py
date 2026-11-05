"""add uq party address use registration; one DDL statement per direction."""
from alembic import op

revision = '0069'
down_revision = '0068'
branch_labels = None
depends_on = None

UPGRADE = 'ALTER TABLE party_address_use ADD CONSTRAINT uq_party_address_use_registration UNIQUE (tenant_id, company_id, address_id, purpose, registration_id)'
DOWNGRADE = 'ALTER TABLE party_address_use DROP INDEX uq_party_address_use_registration'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
