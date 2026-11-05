"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_import_artifact ADD KEY ix_voucher_import_artifact_expiry (tenant_id,company_id,expires_at,id)'
DOWN = 'ALTER TABLE voucher_import_artifact DROP INDEX ix_voucher_import_artifact_expiry'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
