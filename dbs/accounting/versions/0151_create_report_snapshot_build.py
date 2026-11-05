"""report_snapshot_build; one atomic CREATE with scoped constraints."""
from alembic import op

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_snapshot_build (
	status VARCHAR(20) NOT NULL,
	attempt INTEGER NOT NULL,
	lease_until DATETIME(6),
	completed_facts BIGINT NOT NULL,
	manifest JSON,
	evidence JSON,
	failure_code VARCHAR(60),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_snapshot_build PRIMARY KEY (id),
	CONSTRAINT ck_report_snapshot_build_report_snapshot_build_valid CHECK (status IN ('QUEUED','RUNNING','COMPLETE','FAILED') AND attempt >= 0 AND completed_facts >= 0),
	CONSTRAINT uq_report_snapshot_build_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_report_snapshot_build_report_snapshot_build_version CHECK (row_version > 0),
	INDEX ix_report_snapshot_build_page (tenant_id, company_id, id),
	INDEX ix_report_snapshot_build_tenant_id (tenant_id),
	INDEX ix_report_snapshot_build_work (tenant_id, company_id, status, id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_snapshot_build")
