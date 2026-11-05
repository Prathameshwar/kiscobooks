"""report_source_epoch; one atomic CREATE, with scoped constraints."""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_source_epoch (
	status VARCHAR(20) NOT NULL,
	active_generation_id BINARY(16),
	head_sequence BIGINT NOT NULL,
	snapshot_id BINARY(16) NOT NULL,
	owner_generation BIGINT NOT NULL,
	schema_hash VARCHAR(64) NOT NULL,
	scope_hash VARCHAR(64) NOT NULL,
	permission_hash VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_source_epoch PRIMARY KEY (id),
	CONSTRAINT ck_report_source_epoch_report_source_epoch_valid CHECK (head_sequence >= 0 AND status IN ('BUILDING','READY','QUARANTINED')),
	CONSTRAINT uq_report_source_epoch_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_source_epoch_active_generation_id FOREIGN KEY(tenant_id, company_id, active_generation_id) REFERENCES report_generation (tenant_id, company_id, id),
	INDEX ix_report_source_epoch_page (tenant_id, company_id, id),
	INDEX ix_report_source_epoch_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_source_epoch")
