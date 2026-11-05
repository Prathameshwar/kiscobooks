"""Immutable statutory GST allocations; one reversible DDL."""
from alembic import op

revision = "0228"
down_revision = "0227"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE gst_return_record (
      id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL, company_id BINARY(16) NOT NULL,
      row_version INT NOT NULL, created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
      created_by BINARY(16) NULL, updated_by BINARY(16) NULL,
      registration_id BINARY(16) NOT NULL, return_date DATE NOT NULL, event_date DATE NOT NULL,
      category VARCHAR(32) NOT NULL, source_entity VARCHAR(32) NOT NULL, source_id BINARY(16) NULL,
      original_record_id BINARY(16) NULL, reference VARCHAR(120) NOT NULL, evidence_hash VARCHAR(64) NOT NULL,
      currency VARCHAR(3) NOT NULL, conversion_rate DECIMAL(19,8) NULL, taxable DECIMAL(19,4) NOT NULL, igst DECIMAL(19,4) NOT NULL,
      cgst DECIMAL(19,4) NOT NULL, sgst DECIMAL(19,4) NOT NULL, cess DECIMAL(19,4) NOT NULL,
      place_of_supply VARCHAR(2) NULL, recipient VARCHAR(20) NULL, is_advance BOOL NOT NULL,
      credit_head VARCHAR(4) NULL, coverage_area VARCHAR(20) NULL, coverage_status VARCHAR(20) NULL,
      covered_sequence BIGINT NULL, explanation VARCHAR(1000) NOT NULL,
      PRIMARY KEY(id), CONSTRAINT uq_gst_return_record_scope UNIQUE(tenant_id,company_id,id),
      KEY ix_gst_return_record_tenant_id(tenant_id),
      CONSTRAINT ck_gst_return_record_gst_return_record_version CHECK(row_version > 0),
      CONSTRAINT fk_gst_return_record_original_record_id FOREIGN KEY(tenant_id,company_id,original_record_id)
        REFERENCES gst_return_record(tenant_id,company_id,id),
      KEY ix_gst_return_record_page(tenant_id,company_id,id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
    """)


def downgrade() -> None:
    op.execute("DROP TABLE gst_return_record")
