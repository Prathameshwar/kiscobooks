"""Bulk voucher import jobs; one DDL statement."""

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

CREATE = """
CREATE TABLE voucher_import_job (
	actor_user_id BINARY(16) NOT NULL,
	kind VARCHAR(40) NOT NULL,
	type_id BINARY(16) NOT NULL,
	type_revision_id BINARY(16) NOT NULL,
	source_format VARCHAR(10) NOT NULL,
	schema_version INTEGER NOT NULL,
	state VARCHAR(20) NOT NULL,
	on_error VARCHAR(30) NOT NULL,
	input_sha256 VARCHAR(64) NOT NULL,
	selection_digest VARCHAR(64),
	voucher_count INTEGER NOT NULL,
	valid_count INTEGER NOT NULL,
	warning_count INTEGER NOT NULL,
	invalid_count INTEGER NOT NULL,
	created_count INTEGER NOT NULL,
	failed_count INTEGER NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_voucher_import_job PRIMARY KEY (id),
	CONSTRAINT ck_voucher_import_job_counts CHECK (schema_version = 1 AND voucher_count BETWEEN 1 AND 500 AND valid_count >= 0 AND warning_count >= 0 AND invalid_count >= 0 AND created_count >= 0 AND failed_count >= 0),
	CONSTRAINT ck_voucher_import_job_source_format CHECK (source_format IN ('CSV', 'XLSX', 'JSON')),
	CONSTRAINT ck_voucher_import_job_kind CHECK (kind IN ('PURCHASE')),
	CONSTRAINT uq_voucher_import_job_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_voucher_import_job_on_error CHECK (on_error IN ('STOP', 'CONTINUE_INDEPENDENT')),
	CONSTRAINT ck_voucher_import_job_state CHECK (state IN ('STAGED', 'VALIDATING', 'READY', 'COMMITTING', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED')),
	KEY ix_voucher_import_job_actor (tenant_id, company_id, actor_user_id, id),
	KEY ix_voucher_import_job_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_import_job")
