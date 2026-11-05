"""Shared import storage: import_template_snapshot; one reversible DDL."""
from alembic import op

revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE import_template_snapshot (
	actor_user_id BINARY(16) NOT NULL, 
	definition VARCHAR(40) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	snapshot JSON NULL, 
	expires_at DATETIME(6) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_import_template_snapshot PRIMARY KEY (id), 
	CONSTRAINT uq_import_template_snapshot_scope UNIQUE (tenant_id, company_id, id),
KEY ix_import_template_expiry (tenant_id, company_id, expires_at, id),
KEY ix_import_template_snapshot_page (tenant_id, company_id, id),
KEY ix_import_template_snapshot_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE import_template_snapshot")
