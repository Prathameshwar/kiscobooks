"""add template version space. One DDL statement per revision."""
from alembic import op
revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE template_version ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE template_version DROP COLUMN space_id')
