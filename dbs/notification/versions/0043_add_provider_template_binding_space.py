"""add provider template binding space. One DDL statement per revision."""
from alembic import op
revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE provider_template_binding ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE provider_template_binding DROP COLUMN space_id')
