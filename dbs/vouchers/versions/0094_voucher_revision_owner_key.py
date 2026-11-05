"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_revision ADD CONSTRAINT uq_voucher_revision_owner UNIQUE (tenant_id,company_id,voucher_id,id)'
DOWN = 'ALTER TABLE voucher_revision DROP INDEX uq_voucher_revision_owner'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
