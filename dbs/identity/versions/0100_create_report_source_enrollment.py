"""Durable company setup: report_source_enrollment; one atomic DDL."""
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE report_source_enrollment (
	company_id BINARY(16) NOT NULL,
	status VARCHAR(20) NOT NULL,
	revision INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_source_enrollment PRIMARY KEY (id),
	CONSTRAINT uq_report_enrollment_company UNIQUE (tenant_id, company_id),
	CONSTRAINT fk_report_source_enrollment_tenant_id FOREIGN KEY(tenant_id, company_id) REFERENCES company (tenant_id, id),
	KEY ix_report_enrollment_discovery (status, id),
	KEY ix_report_source_enrollment_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    # Deployment rollback must retain setup/audit evidence until explicitly archived.
    op.execute("DROP TABLE report_source_enrollment")
