"""add delivery attachment space. One DDL statement per revision."""
from alembic import op
revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE delivery_attachment ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE delivery_attachment DROP COLUMN space_id')
