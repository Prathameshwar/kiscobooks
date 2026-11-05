"""Attempt-scoped frozen hierarchy locators; one reversible CREATE TABLE."""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_hierarchy_node (
	job_id BINARY(16) NOT NULL, 
	batch_id BINARY(16) NOT NULL, 
	attempt INTEGER NOT NULL, 
	period VARCHAR(12) NOT NULL, 
	node_key VARCHAR(48) NOT NULL, 
	parent_key VARCHAR(48) NOT NULL, 
	ordinal BIGINT NOT NULL, 
	depth INTEGER NOT NULL, 
	is_zero BOOL NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_report_hierarchy_node PRIMARY KEY (id), 
	CONSTRAINT fk_report_hierarchy_node_attempt FOREIGN KEY(tenant_id, company_id, job_id, attempt) REFERENCES report_job_attempt (tenant_id, company_id, job_id, attempt), 
	CONSTRAINT uq_report_hierarchy_node_key UNIQUE (tenant_id, company_id, job_id, attempt, period, node_key), 
	CONSTRAINT ck_report_hierarchy_node_report_hierarchy_node_bounds CHECK (attempt > 0 AND ordinal > 0 AND depth >= 0), 
	CONSTRAINT ck_report_hierarchy_node_report_hierarchy_node_period CHECK (period IN ('CURRENT','COMPARATIVE')), 
	CONSTRAINT uq_report_hierarchy_node_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_report_hierarchy_node_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES report_job (tenant_id, company_id, id), 
	CONSTRAINT fk_report_hierarchy_node_batch_id FOREIGN KEY(tenant_id, company_id, batch_id) REFERENCES report_result_batch (tenant_id, company_id, id),
	INDEX ix_report_hierarchy_node_children (tenant_id, company_id, job_id, attempt, period, parent_key, ordinal),
	INDEX ix_report_hierarchy_node_page (tenant_id, company_id, id),
	INDEX ix_report_hierarchy_node_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE report_hierarchy_node")
