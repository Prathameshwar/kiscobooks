"""Indexed immutable native draft identities per imported cohort; one CREATE."""

from alembic import op
from sqlalchemy import text

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_opening_import_claim (
        control_id BINARY(16) NOT NULL, source_key VARCHAR(100) NOT NULL,
        job_id BINARY(16) NOT NULL, voucher_id BINARY(16) NOT NULL,
        company_id BINARY(16) NOT NULL, row_version INTEGER NOT NULL,
        id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_stock_opening_import_claim PRIMARY KEY (id),
        CONSTRAINT uq_opening_import_claim_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT uq_opening_import_cohort UNIQUE (tenant_id, company_id, control_id, source_key, voucher_id),
        CONSTRAINT fk_opening_import_claim_job FOREIGN KEY (tenant_id, company_id, job_id)
            REFERENCES stock_opening_import (tenant_id, company_id, id),
        CONSTRAINT fk_opening_import_claim_voucher FOREIGN KEY (tenant_id, company_id, voucher_id)
            REFERENCES voucher (tenant_id, company_id, id),
        CONSTRAINT ck_stock_opening_import_claim_opening_import_claim_version CHECK (row_version > 0),
        KEY ix_opening_import_claim_job (tenant_id, company_id, job_id, id),
        KEY ix_opening_import_claim_voucher (tenant_id, company_id, voucher_id, id),
        KEY ix_stock_opening_import_claim_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_opening_import_claim LIMIT 1")).first():
        raise RuntimeError("archive retained opening import cohort evidence before downgrade")
    op.execute("DROP TABLE stock_opening_import_claim")
