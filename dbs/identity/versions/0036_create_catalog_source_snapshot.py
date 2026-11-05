"""Identity-owned catalog_source_snapshot; one CREATE/DROP, no seed data."""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_source_snapshot (
    company_id BINARY(16) NOT NULL, 
    request_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    generated_at DATETIME(6) NOT NULL, 
    expires_at DATETIME(6) NOT NULL, 
    manifest JSON NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_catalog_source_snapshot PRIMARY KEY (id), 
    CONSTRAINT uq_catalog_source_snapshot_scope UNIQUE (tenant_id, company_id, id), 
    CONSTRAINT uq_catalog_source_snapshot_request UNIQUE (tenant_id, company_id, request_id), 
    CONSTRAINT ck_catalog_source_snapshot_catalog_snapshot_version CHECK (source_version >= 1)
,
  KEY ix_catalog_source_snapshot_expiry (tenant_id, expires_at, id),
  KEY ix_catalog_source_snapshot_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_source_snapshot")
