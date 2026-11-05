"""add routing rule space. One DDL statement per revision."""
from alembic import op
revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE routing_rule ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE routing_rule DROP COLUMN space_id')
