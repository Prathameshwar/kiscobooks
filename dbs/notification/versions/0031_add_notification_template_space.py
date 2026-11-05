"""add notification template space. One DDL statement per revision."""
from alembic import op
revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE notification_template ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE notification_template DROP COLUMN space_id')
