"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_import_row ADD CONSTRAINT fk_voucher_import_row_voucher FOREIGN KEY (tenant_id,company_id,voucher_id) REFERENCES voucher(tenant_id,company_id,id)'
DOWN = 'ALTER TABLE voucher_import_row DROP FOREIGN KEY fk_voucher_import_row_voucher'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
