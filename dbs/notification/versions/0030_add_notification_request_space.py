"""add notification request space. One DDL statement per revision."""
from alembic import op
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE notification_request ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE notification_request DROP COLUMN space_id')
