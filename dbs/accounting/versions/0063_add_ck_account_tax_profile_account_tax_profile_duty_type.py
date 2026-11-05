"""add ck account tax profile account tax profile duty type; one DDL statement per direction."""
from alembic import op

revision = '0063'
down_revision = '0062'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_tax_profile ADD CONSTRAINT ck_account_tax_profile_account_tax_profile_duty_type CHECK (duty_type IN ('GST', 'VAT', 'TDS', 'TCS', 'CESS', 'EXCISE', 'OTHER'))"
DOWNGRADE = 'ALTER TABLE account_tax_profile DROP CHECK ck_account_tax_profile_account_tax_profile_duty_type'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
