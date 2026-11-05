"""Catalog user_group_projection: complete verified source materialization; one DDL."""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE user_group_projection (
    is_active BOOL NOT NULL, 
    company_id BINARY(16) NOT NULL, 
    source_id BINARY(16) NOT NULL, 
    source_version BIGINT NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_user_group_projection PRIMARY KEY (id), 
    CONSTRAINT uq_group_projection_source UNIQUE (tenant_id, company_id, source_id), 
    CONSTRAINT ck_user_group_projection_group_source_version CHECK (source_version > 0),
    KEY ix_user_group_projection_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE user_group_projection")
