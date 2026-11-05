"""add notification delivery space. One DDL statement per revision."""
from alembic import op
revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE notification_delivery ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE notification_delivery DROP COLUMN space_id')
