"""Create bulk_change_set_effect; one reversible DDL."""
from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bulk_change_set_effect (
	job_id BINARY(16) NOT NULL,
	change_set_id BINARY(16) NOT NULL,
	logical_key VARCHAR(64) NOT NULL,
	accepted_revision INTEGER NOT NULL,
	action_hash VARCHAR(64) NOT NULL,
	results JSON NOT NULL,
	source_pins JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bulk_change_set_effect PRIMARY KEY (id),
	CONSTRAINT uq_bulk_change_set_effect_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_change_set_effect_version CHECK (row_version >= 1),
	CONSTRAINT fk_bulk_change_set_effect_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES bulk_job (tenant_id, company_id, id),
	CONSTRAINT fk_bulk_change_set_effect_change_set_id FOREIGN KEY(tenant_id, company_id, job_id, change_set_id) REFERENCES bulk_change_set (tenant_id, company_id, job_id, id),
	CONSTRAINT uq_bulk_change_set_effect_key UNIQUE (tenant_id, company_id, job_id, logical_key),
	CONSTRAINT ck_bulk_change_set_effect_revision CHECK (accepted_revision >= 1),
    INDEX ix_bulk_change_set_effect_job (tenant_id, company_id, job_id, id),
    INDEX ix_bulk_change_set_effect_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bulk_change_set_effect")
