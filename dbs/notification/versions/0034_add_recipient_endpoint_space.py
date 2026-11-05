"""add recipient endpoint space. One DDL statement per revision."""
from alembic import op
revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE recipient_endpoint ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE recipient_endpoint DROP COLUMN space_id')
