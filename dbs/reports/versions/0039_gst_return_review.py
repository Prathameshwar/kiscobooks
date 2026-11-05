"""Immutable preparation review and external filing evidence; one reversible DDL."""
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE gst_return_review (
      id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL, company_id BINARY(16) NOT NULL,
      row_version INT NOT NULL, created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
      created_by BINARY(16) NULL, updated_by BINARY(16) NULL, job_id BINARY(16) NOT NULL,
      registration_id BINARY(16) NOT NULL, period VARCHAR(10) NOT NULL, state VARCHAR(20) NOT NULL,
      reference VARCHAR(120) NOT NULL, evidence_hash VARCHAR(64) NOT NULL, filed_date DATE NULL,
      filed_period_key VARCHAR(50) NULL, PRIMARY KEY(id),
      KEY ix_gst_return_review_tenant_id(tenant_id),
      CONSTRAINT uq_gst_return_review_scope UNIQUE(tenant_id,company_id,id),
      CONSTRAINT uq_gst_review_state UNIQUE(tenant_id,company_id,job_id,state),
      CONSTRAINT uq_gst_filed_period UNIQUE(tenant_id,company_id,filed_period_key),
      CONSTRAINT fk_gst_return_review_job_id FOREIGN KEY(tenant_id,company_id,job_id)
        REFERENCES report_job(tenant_id,company_id,id),
      KEY ix_gst_return_review_page(tenant_id,company_id,id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
    """)


def downgrade() -> None:
    op.execute("DROP TABLE gst_return_review")
