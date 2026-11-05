"""add template variant space. One DDL statement per revision."""
from alembic import op
revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE template_variant ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE template_variant DROP COLUMN space_id')
