"""add voucher send state space. One DDL statement per revision."""
from alembic import op
revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('ALTER TABLE voucher_send_state ADD COLUMN space_id BINARY(16) NULL')

def downgrade() -> None:
    op.execute('ALTER TABLE voucher_send_state DROP COLUMN space_id')
