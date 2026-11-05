"""Shared import storage: import_artifact; one reversible DDL."""
from alembic import op

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_artifact (
	revision_id BINARY(16) NOT NULL, 
	filename VARCHAR(120) NOT NULL, 
	format VARCHAR(5) NOT NULL, 
	content_sha256 VARCHAR(64) NOT NULL, 
	byte_count INTEGER NOT NULL, 
	expires_at DATETIME(6) NOT NULL, 
	content MEDIUMBLOB NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_artifact PRIMARY KEY (id), 
	CONSTRAINT uq_import_artifact_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_import_artifact_revision_id FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES import_job_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_import_artifact_import_artifact_bounds CHECK (byte_count BETWEEN 0 AND 8388608),
KEY ix_import_artifact_expiry (tenant_id, company_id, expires_at, id),
KEY ix_import_artifact_page (tenant_id, company_id, id),
KEY ix_import_artifact_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_artifact")
