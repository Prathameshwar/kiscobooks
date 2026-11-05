"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_import_effect ADD CONSTRAINT fk_voucher_import_effect_revision FOREIGN KEY (tenant_id,company_id,voucher_id,revision_id) REFERENCES voucher_revision(tenant_id,company_id,voucher_id,id)'
DOWN = 'ALTER TABLE voucher_import_effect DROP FOREIGN KEY fk_voucher_import_effect_revision'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
