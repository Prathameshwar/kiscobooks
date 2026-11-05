"""Identity-owned catalog_source_generation; one CREATE/DROP, no seed data."""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_source_generation (
    version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_catalog_source_generation PRIMARY KEY (id), 
    CONSTRAINT uq_catalog_source_generation_tenant UNIQUE (tenant_id), 
    CONSTRAINT ck_catalog_source_generation_catalog_source_version CHECK (version >= 1)
,
  KEY ix_catalog_source_generation_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_source_generation")
