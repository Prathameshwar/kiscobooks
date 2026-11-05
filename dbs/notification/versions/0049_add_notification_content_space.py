"""add notification content space. One DDL statement per revision."""
from alembic import op
revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE notification_content ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE notification_content DROP COLUMN space_id')
