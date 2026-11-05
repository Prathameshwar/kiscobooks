"""add provider event space. One DDL statement per revision."""
from alembic import op
revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE provider_event ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE provider_event DROP COLUMN space_id')
