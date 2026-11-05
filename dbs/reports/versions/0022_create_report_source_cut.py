"""report_source_cut; one atomic CREATE, with scoped constraints."""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_source_cut (
	epoch_id BINARY(16) NOT NULL,
	generation_id BINARY(16) NOT NULL,
	sequence BIGINT NOT NULL,
	manifest JSON NOT NULL,
	verification JSON,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_source_cut PRIMARY KEY (id),
	CONSTRAINT uq_report_source_cut_generation UNIQUE (tenant_id, company_id, generation_id),
	CONSTRAINT ck_report_source_cut_report_source_cut_sequence CHECK (sequence >= 0),
	CONSTRAINT uq_report_source_cut_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_source_cut_epoch_id FOREIGN KEY(tenant_id, company_id, epoch_id) REFERENCES report_source_epoch (tenant_id, company_id, id),
	CONSTRAINT fk_report_source_cut_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id),
	INDEX ix_report_source_cut_page (tenant_id, company_id, id),
	INDEX ix_report_source_cut_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_source_cut")
