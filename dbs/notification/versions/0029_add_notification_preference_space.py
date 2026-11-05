"""add notification preference space. One DDL statement per revision."""
from alembic import op
revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE notification_preference ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE notification_preference DROP COLUMN space_id')
