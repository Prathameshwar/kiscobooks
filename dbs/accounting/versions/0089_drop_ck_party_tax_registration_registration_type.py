"""drop the party registration type check before widening it; one DDL statement per direction."""
from alembic import op

revision = '0089'
down_revision = '0088'
branch_labels = None
depends_on = None

# Downgrade restores the four-type check; it fails while rows use a newer type, which must be
# retyped or retired first (MySQL validates a CHECK against existing rows).

UPGRADE = 'ALTER TABLE party_tax_registration DROP CHECK ck_party_tax_registration_party_tax_registration_registr_dbc8'
DOWNGRADE = "ALTER TABLE party_tax_registration ADD CONSTRAINT ck_party_tax_registration_party_tax_registration_registr_dbc8 CHECK (registration_type IN ('REGULAR', 'COMPOSITION', 'UNREGISTERED', 'OTHER'))"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
