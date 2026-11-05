"""drop uq party address use 0; one DDL statement per direction."""
from alembic import op

revision = '0070'
down_revision = '0069'
branch_labels = None
depends_on = None

UPGRADE = 'ALTER TABLE party_address_use DROP INDEX uq_party_address_use_0'
DOWNGRADE = 'ALTER TABLE party_address_use ADD CONSTRAINT uq_party_address_use_0 UNIQUE (tenant_id, company_id, address_id, purpose)'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
