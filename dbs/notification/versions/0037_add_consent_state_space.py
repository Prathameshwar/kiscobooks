"""add consent state space. One DDL statement per revision."""
from alembic import op
revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE consent_state ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE consent_state DROP COLUMN space_id')
