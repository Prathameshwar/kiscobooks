"""Identity-owned catalog_source_page; one CREATE/DROP, no seed data."""
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_source_page (
    company_id BINARY(16) NOT NULL, 
    snapshot_id BINARY(16) NOT NULL, 
    page_number INTEGER NOT NULL, 
    content_sha256 VARCHAR(64) NOT NULL, 
    payload JSON NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_catalog_source_page PRIMARY KEY (id), 
    CONSTRAINT uq_catalog_source_page_number UNIQUE (tenant_id, company_id, snapshot_id,
        page_number),
        CONSTRAINT fk_catalog_source_page_snapshot FOREIGN KEY(tenant_id, company_id,
        snapshot_id) REFERENCES catalog_source_snapshot (tenant_id, company_id, id),
    CONSTRAINT ck_catalog_source_page_catalog_source_page_nonnegative CHECK (page_number >= 0)
,
  KEY ix_catalog_source_page_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE catalog_source_page")
