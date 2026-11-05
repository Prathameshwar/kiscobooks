"""Durable automatic source health; one DDL statement."""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_readiness (
	owner_sequence BIGINT,
	checked_at DATETIME(6),
	next_attempt_at DATETIME(6) NOT NULL,
	failure_code VARCHAR(60),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_readiness PRIMARY KEY (id),
	CONSTRAINT uq_report_readiness_company UNIQUE (tenant_id, company_id),
	CONSTRAINT uq_report_readiness_scope UNIQUE (tenant_id, company_id, id),
	INDEX ix_report_readiness_page (tenant_id, company_id, id),
	INDEX ix_report_readiness_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    # Operational rollback disables workers; never remove retained report evidence.
    op.execute("DROP TABLE report_readiness")
