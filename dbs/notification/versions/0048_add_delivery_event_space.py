"""add delivery event space. One DDL statement per revision."""
from alembic import op
revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE delivery_event ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE delivery_event DROP COLUMN space_id')
