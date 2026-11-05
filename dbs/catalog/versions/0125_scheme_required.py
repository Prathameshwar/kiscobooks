"""Add native category scheme membership requirement.

Downgrade preserves rows and refuses incompatible retained dated data.
"""
from alembic import op

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None

_ALTER = 'ALTER TABLE category_scheme ADD COLUMN is_required TINYINT(1) NOT NULL DEFAULT 0'


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute('ALTER TABLE category_scheme DROP COLUMN is_required')
