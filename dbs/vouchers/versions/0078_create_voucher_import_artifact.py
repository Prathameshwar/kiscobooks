"""Private uploaded import files; one DDL statement."""

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

CREATE = """
CREATE TABLE voucher_import_artifact (
	job_id BINARY(16) NOT NULL,
	media_type VARCHAR(100) NOT NULL,
	content_sha256 VARCHAR(64) NOT NULL,
	byte_count INTEGER NOT NULL,
	content MEDIUMBLOB NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_voucher_import_artifact PRIMARY KEY (id),
	CONSTRAINT ck_voucher_import_artifact_bytes CHECK (byte_count BETWEEN 0 AND 8388608),
	CONSTRAINT uq_voucher_import_artifact_job UNIQUE (tenant_id, company_id, job_id),
	CONSTRAINT fk_voucher_import_artifact_job FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES voucher_import_job (tenant_id, company_id, id),
	CONSTRAINT uq_voucher_import_artifact_scope UNIQUE (tenant_id, company_id, id),
	KEY ix_voucher_import_artifact_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_import_artifact")
