"""Dated outward-return profile; one reversible atomic DDL."""
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE company_gst_outward_profile (
      id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL, company_id BINARY(16) NOT NULL,
      registration_id BINARY(16) NOT NULL, annual_turnover DECIMAL(19,4) NOT NULL,
      currency VARCHAR(3) NOT NULL, rule_14a BOOL NOT NULL, reference VARCHAR(120) NOT NULL,
      evidence_hash VARCHAR(64) NOT NULL, valid_from DATE NOT NULL, valid_to DATE NULL,
      created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
      created_by BINARY(16) NULL, updated_by BINARY(16) NULL,
      PRIMARY KEY(id), KEY ix_company_gst_outward_profile_tenant_id(tenant_id),
      CONSTRAINT uq_gst_outward_profile_start UNIQUE(tenant_id,company_id,registration_id,valid_from),
      CONSTRAINT fk_gst_outward_company FOREIGN KEY(company_id) REFERENCES company(id),
      CONSTRAINT fk_gst_outward_registration FOREIGN KEY(registration_id) REFERENCES company_tax_registration(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
    """)


def downgrade() -> None:
    op.execute("DROP TABLE company_gst_outward_profile")
