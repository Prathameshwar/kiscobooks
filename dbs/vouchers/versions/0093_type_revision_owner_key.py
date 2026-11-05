"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_type_revision ADD CONSTRAINT uq_voucher_type_revision_owner UNIQUE (tenant_id,company_id,type_id,id)'
DOWN = 'ALTER TABLE voucher_type_revision DROP INDEX uq_voucher_type_revision_owner'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
