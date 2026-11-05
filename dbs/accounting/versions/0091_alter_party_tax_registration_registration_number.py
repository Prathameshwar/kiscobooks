"""allow UNREGISTERED/OVERSEAS party registrations without a number; one DDL statement per direction."""
from alembic import op

revision = '0091'
down_revision = '0090'
branch_labels = None
depends_on = None

# Downgrade fails while number-less UNREGISTERED/OVERSEAS rows exist (strict mode refuses
# NULL into NOT NULL), so it is supported only before such rows have been recorded.

UPGRADE = 'ALTER TABLE party_tax_registration MODIFY COLUMN registration_number VARCHAR(80) NULL'
DOWNGRADE = 'ALTER TABLE party_tax_registration MODIFY COLUMN registration_number VARCHAR(80) NOT NULL'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
