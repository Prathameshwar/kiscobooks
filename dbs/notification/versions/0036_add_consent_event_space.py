"""add consent event space. One DDL statement per revision."""
from alembic import op
revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE consent_event ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE consent_event DROP COLUMN space_id')
