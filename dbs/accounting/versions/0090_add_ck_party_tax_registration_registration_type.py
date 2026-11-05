"""widen party registration types (SEZ, UIN, overseas, casual, NRTP); one DDL statement per direction."""
from alembic import op

revision = '0090'
down_revision = '0089'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE party_tax_registration ADD CONSTRAINT ck_party_tax_registration_party_tax_registration_registr_dbc8 CHECK (registration_type IN ('REGULAR', 'COMPOSITION', 'UNREGISTERED', 'SEZ_UNIT', 'SEZ_DEVELOPER', 'UIN', 'OVERSEAS', 'CASUAL', 'NRTP', 'OTHER'))"
DOWNGRADE = 'ALTER TABLE party_tax_registration DROP CHECK ck_party_tax_registration_party_tax_registration_registr_dbc8'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
