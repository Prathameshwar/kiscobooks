"""report_snapshot_batch; one atomic CREATE with scoped constraints."""
from alembic import op

revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_snapshot_batch (
	build_id BINARY(16) NOT NULL,
	attempt INTEGER NOT NULL,
	first_ordinal BIGINT NOT NULL,
	fact_count INTEGER NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	facts JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_snapshot_batch PRIMARY KEY (id),
	CONSTRAINT uq_report_snapshot_batch_ordinal UNIQUE (tenant_id, company_id, build_id, attempt, first_ordinal),
	CONSTRAINT ck_report_snapshot_batch_report_snapshot_batch_valid CHECK (attempt > 0 AND first_ordinal > 0 AND fact_count BETWEEN 1 AND 200),
	CONSTRAINT uq_report_snapshot_batch_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_report_snapshot_batch_report_snapshot_batch_version CHECK (row_version > 0),
	CONSTRAINT fk_report_snapshot_batch_build_id FOREIGN KEY(tenant_id, company_id, build_id) REFERENCES report_snapshot_build (tenant_id, company_id, id),
	INDEX ix_report_snapshot_batch_page (tenant_id, company_id, id),
	INDEX ix_report_snapshot_batch_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_snapshot_batch")
