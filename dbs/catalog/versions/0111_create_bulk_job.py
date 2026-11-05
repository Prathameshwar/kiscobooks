"""Create bulk_job; one reversible DDL."""
from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bulk_job (
	actor_user_id BINARY(16) NOT NULL,
	kind VARCHAR(10) NOT NULL,
	mode VARCHAR(12) NOT NULL,
	atomicity VARCHAR(12) NOT NULL,
	on_error VARCHAR(24) NOT NULL,
	state VARCHAR(12) NOT NULL,
	revision INTEGER NOT NULL,
	schema_version INTEGER NOT NULL,
	input_hash VARCHAR(64) NOT NULL,
	selection_digest VARCHAR(64) NULL,
	policy_generation BIGINT NULL,
	source_version BIGINT NULL,
	identity_digest VARCHAR(64) NULL,
	record_count INTEGER NOT NULL,
	completed_count INTEGER NOT NULL,
	invalid_count INTEGER NOT NULL,
	selected_keys JSON NULL,
	expires_at DATETIME(6) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bulk_job PRIMARY KEY (id),
	CONSTRAINT uq_bulk_job_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_job_version CHECK (row_version >= 1),
	CONSTRAINT ck_bulk_job_kind CHECK (kind IN ('IMPORT','UPDATE')),
	CONSTRAINT ck_bulk_job_mode CHECK (mode IN ('CREATE_ONLY','UPDATE_ONLY','UPSERT')),
	CONSTRAINT ck_bulk_job_atomicity CHECK (atomicity IN ('CHANGE_SET','ATOMIC')),
	CONSTRAINT ck_bulk_job_on_error CHECK (on_error IN ('STOP','CONTINUE_INDEPENDENT')),
	CONSTRAINT ck_bulk_job_state CHECK (state IN ('STAGED','VALIDATING','READY','QUEUED','RUNNING','SUCCEEDED','PARTIAL','FAILED','CANCELLED')),
	CONSTRAINT ck_bulk_job_bounds CHECK (revision >= 1 AND record_count BETWEEN 1 AND 2000),
	CONSTRAINT ck_bulk_job_completed CHECK (completed_count >= 0 AND completed_count <= record_count),
	CONSTRAINT ck_bulk_job_invalid CHECK (invalid_count >= 0 AND invalid_count <= record_count),
    INDEX ix_bulk_job_actor (tenant_id, company_id, actor_user_id, id),
    INDEX ix_bulk_job_tenant_id (tenant_id),
    INDEX ix_bulk_job_work (tenant_id, company_id, state, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bulk_job")
