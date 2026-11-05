"""Catalog company_feature_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE company_feature_projection (
    source_company_id BINARY(16) NOT NULL, 
    feature_key VARCHAR(60) NOT NULL, 
    is_enabled BOOL NOT NULL, 
    locked_at DATETIME(6) NULL,
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_company_feature_projection PRIMARY KEY (id), 
    CONSTRAINT uq_feature_projection_source UNIQUE (tenant_id, company_id, source_id), 
    CONSTRAINT ck_company_feature_projection_feature_source_version CHECK (source_version > 0),
    KEY ix_company_feature_projection_tenant_id (tenant_id),
    KEY ix_feature_projection_lookup_0 (tenant_id, company_id, feature_key)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_feature_projection")
