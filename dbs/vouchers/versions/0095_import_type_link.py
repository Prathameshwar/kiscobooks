"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

UP = 'ALTER TABLE voucher_import_job ADD CONSTRAINT fk_voucher_import_job_type FOREIGN KEY (tenant_id,company_id,type_id,type_revision_id) REFERENCES voucher_type_revision(tenant_id,company_id,type_id,id)'
DOWN = 'ALTER TABLE voucher_import_job DROP FOREIGN KEY fk_voucher_import_job_type'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
