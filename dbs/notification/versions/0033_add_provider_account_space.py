"""add provider account space. One DDL statement per revision."""
from alembic import op
revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE provider_account ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE provider_account DROP COLUMN space_id')
