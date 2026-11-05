"""add suppression space. One DDL statement per revision."""
from alembic import op
revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE suppression ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE suppression DROP COLUMN space_id')
