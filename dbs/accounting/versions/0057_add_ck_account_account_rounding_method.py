"""add ck account account rounding method; one DDL statement per direction."""
from alembic import op

revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account ADD CONSTRAINT ck_account_account_rounding_method CHECK (rounding_method IN ('NONE', 'NORMAL', 'UP', 'DOWN'))"
DOWNGRADE = 'ALTER TABLE account DROP CHECK ck_account_account_rounding_method'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
