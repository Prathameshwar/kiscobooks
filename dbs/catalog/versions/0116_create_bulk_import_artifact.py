"""Create bulk_import_artifact; one reversible DDL."""
from alembic import op

revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bulk_import_artifact (
	job_id BINARY(16) NOT NULL,
	content_type VARCHAR(120) NOT NULL,
	content_sha256 VARCHAR(64) NOT NULL,
	byte_count INTEGER NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	content MEDIUMBLOB NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bulk_import_artifact PRIMARY KEY (id),
	CONSTRAINT uq_bulk_import_artifact_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_import_artifact_version CHECK (row_version >= 1),
	CONSTRAINT fk_bulk_import_artifact_job_id FOREIGN KEY(tenant_id, company_id, job_id) REFERENCES bulk_job (tenant_id, company_id, id),
	CONSTRAINT ck_bulk_import_artifact_bounds CHECK (byte_count BETWEEN 0 AND 8388608),
    INDEX ix_bulk_import_artifact_expiry (tenant_id, company_id, expires_at, id),
    INDEX ix_bulk_import_artifact_job (tenant_id, company_id, job_id, id),
    INDEX ix_bulk_import_artifact_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bulk_import_artifact")
