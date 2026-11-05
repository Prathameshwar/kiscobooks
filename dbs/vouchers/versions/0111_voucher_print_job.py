"""Durable scoped PDF work; a single reversible CREATE statement."""

from alembic import op
from sqlalchemy import text

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE voucher_print_job (
        voucher_id BINARY(16) NOT NULL, revision_id BINARY(16) NOT NULL,
        permission_hash VARCHAR(64) NOT NULL, request_hash VARCHAR(64) NOT NULL,
        snapshot JSON NOT NULL, status VARCHAR(16) NOT NULL, attempt INTEGER NOT NULL,
        lease_until DATETIME(6), content_hash VARCHAR(64), size_bytes INTEGER,
        failure_code VARCHAR(40), company_id BINARY(16) NOT NULL,
        row_version INTEGER NOT NULL, id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_voucher_print_job PRIMARY KEY (id),
        CONSTRAINT ck_voucher_print_job_status CHECK (status IN ('PENDING','RUNNING','READY','FAILED')),
        CONSTRAINT ck_voucher_print_job_attempt CHECK (attempt >= 0 AND attempt <= 3),
        CONSTRAINT fk_print_job_voucher FOREIGN KEY (tenant_id, company_id, voucher_id)
            REFERENCES voucher (tenant_id, company_id, id),
        CONSTRAINT fk_print_job_revision FOREIGN KEY (tenant_id, company_id, revision_id)
            REFERENCES voucher_revision (tenant_id, company_id, id),
        KEY ix_voucher_print_job_tenant_id (tenant_id),
        KEY ix_print_job_pending (tenant_id, company_id, status, id),
        KEY ix_print_job_request (tenant_id, company_id, request_hash, permission_hash, id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM voucher_print_job LIMIT 1")).first():
        raise RuntimeError("retain print evidence before downgrading")
    op.execute("DROP TABLE voucher_print_job")
