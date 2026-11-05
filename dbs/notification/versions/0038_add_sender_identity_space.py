"""add sender identity space. One DDL statement per revision."""
from alembic import op
revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE sender_identity ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE sender_identity DROP COLUMN space_id')
