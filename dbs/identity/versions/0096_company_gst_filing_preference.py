"""Dated GST filing preferences; one reversible DDL statement."""
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE company_gst_filing_preference (
      id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
      company_id BINARY(16) NOT NULL, registration_id BINARY(16) NOT NULL,
      frequency VARCHAR(10) NOT NULL, valid_from DATE NOT NULL, valid_to DATE NULL,
      created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
      created_by BINARY(16) NULL, updated_by BINARY(16) NULL,
      PRIMARY KEY (id),
      KEY ix_company_gst_filing_preference_tenant_id(tenant_id),
      CONSTRAINT uq_gst_filing_start UNIQUE (tenant_id,company_id,registration_id,valid_from),
      CONSTRAINT ck_company_gst_filing_preference_gst_filing_frequency CHECK (frequency IN ('MONTHLY','QRMP')),
      CONSTRAINT fk_gst_filing_company FOREIGN KEY (company_id) REFERENCES company(id),
      CONSTRAINT fk_gst_filing_registration FOREIGN KEY (registration_id) REFERENCES company_tax_registration(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
    """)


def downgrade() -> None:
    op.execute("DROP TABLE company_gst_filing_preference")
