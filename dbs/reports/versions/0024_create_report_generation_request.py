"""Durable source build request; one atomic CREATE with scoped references."""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_generation_request (
	generation_id BINARY(16) NOT NULL,
	strategy VARCHAR(10) NOT NULL,
	parent_cut_id BINARY(16),
	epoch_id BINARY(16),
	target_manifest JSON,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_generation_request PRIMARY KEY (id),
	CONSTRAINT uq_report_generation_request_generation UNIQUE (tenant_id, company_id, generation_id),
	CONSTRAINT ck_report_generation_request_report_generation_request_valid CHECK (strategy IN ('FRESH','REFRESH','COMPACT') AND ((strategy = 'FRESH' AND parent_cut_id IS NULL) OR (strategy <> 'FRESH' AND parent_cut_id IS NOT NULL))),
	CONSTRAINT uq_report_generation_request_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_generation_request_generation_id FOREIGN KEY(tenant_id, company_id, generation_id) REFERENCES report_generation (tenant_id, company_id, id),
	CONSTRAINT fk_report_generation_request_parent_cut_id FOREIGN KEY(tenant_id, company_id, parent_cut_id) REFERENCES report_source_cut (tenant_id, company_id, id),
	CONSTRAINT fk_report_generation_request_epoch_id FOREIGN KEY(tenant_id, company_id, epoch_id) REFERENCES report_source_epoch (tenant_id, company_id, id),
	INDEX ix_report_generation_request_page (tenant_id, company_id, id),
	INDEX ix_report_generation_request_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_generation_request")
