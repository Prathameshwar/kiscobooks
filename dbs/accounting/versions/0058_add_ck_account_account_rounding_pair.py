"""add ck account account rounding pair; one DDL statement per direction."""
from alembic import op

revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account ADD CONSTRAINT ck_account_account_rounding_pair CHECK ((rounding_method = 'NONE' AND rounding_limit IS NULL) OR (rounding_method <> 'NONE' AND rounding_limit IS NOT NULL AND rounding_limit > 0 AND currency_mode <> 'MULTI'))"
DOWNGRADE = 'ALTER TABLE account DROP CHECK ck_account_account_rounding_pair'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
