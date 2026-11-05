"""add party endpoint checkpoint space. One DDL statement per revision."""
from alembic import op
revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE party_endpoint_checkpoint ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE party_endpoint_checkpoint DROP COLUMN space_id')
