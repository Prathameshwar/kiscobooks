"""add delivery attempt space. One DDL statement per revision."""
from alembic import op
revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE delivery_attempt ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE delivery_attempt DROP COLUMN space_id')
