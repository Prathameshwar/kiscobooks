"""tie a missing registration number to UNREGISTERED/OVERSEAS; one DDL statement per direction."""
from alembic import op

revision = '0092'
down_revision = '0091'
branch_labels = None
depends_on = None

# Upgrade fails if an existing UNREGISTERED row carries a number; the API refused UNREGISTERED
# before this revision, so no such row can exist.

UPGRADE = "ALTER TABLE party_tax_registration ADD CONSTRAINT ck_party_tax_registration_party_tax_registration_number CHECK ((registration_type = 'UNREGISTERED' AND registration_number IS NULL) OR registration_type = 'OVERSEAS' OR (registration_type <> 'UNREGISTERED' AND registration_number IS NOT NULL))"
DOWNGRADE = 'ALTER TABLE party_tax_registration DROP CHECK ck_party_tax_registration_party_tax_registration_number'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
