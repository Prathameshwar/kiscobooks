"""add template activation space. One DDL statement per revision."""
from alembic import op
revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE template_activation ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE template_activation DROP COLUMN space_id')
