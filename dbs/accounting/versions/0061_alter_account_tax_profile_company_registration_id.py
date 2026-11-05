"""alter account tax profile company registration id; one DDL statement per direction."""
from alembic import op

revision = '0061'
down_revision = '0060'
branch_labels = None
depends_on = None

UPGRADE = 'ALTER TABLE account_tax_profile MODIFY COLUMN company_registration_id BINARY(16)'
DOWNGRADE = 'ALTER TABLE account_tax_profile MODIFY COLUMN company_registration_id BINARY(16) NOT NULL'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
