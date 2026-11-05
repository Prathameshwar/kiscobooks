"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

UP = "ALTER TABLE voucher_import_job DROP CHECK ck_voucher_import_job_state, DROP CHECK ck_voucher_import_job_source_format, ADD CONSTRAINT ck_voucher_import_job_state CHECK (state IN ('STAGED','VALIDATING','READY','COMMITTING','SUCCEEDED','PARTIAL','FAILED','CANCELLED','EXPIRED')), ADD CONSTRAINT ck_voucher_import_job_source_format CHECK (source_format IN ('CSV','TSV','XLSX','JSON')), ADD COLUMN revision INTEGER NOT NULL DEFAULT 1, ADD KEY ix_voucher_import_job_expiry (tenant_id,company_id,expires_at,id), ADD KEY ix_voucher_import_job_state (tenant_id,company_id,actor_user_id,state,id)"
DOWN = "ALTER TABLE voucher_import_job DROP CHECK ck_voucher_import_job_state, DROP CHECK ck_voucher_import_job_source_format, DROP COLUMN revision, DROP INDEX ix_voucher_import_job_expiry, DROP INDEX ix_voucher_import_job_state, ADD CONSTRAINT ck_voucher_import_job_state CHECK (state IN ('STAGED','VALIDATING','READY','COMMITTING','SUCCEEDED','PARTIAL','FAILED','CANCELLED')), ADD CONSTRAINT ck_voucher_import_job_source_format CHECK (source_format IN ('CSV','XLSX','JSON'))"

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
