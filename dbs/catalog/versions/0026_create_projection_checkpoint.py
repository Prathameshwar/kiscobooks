"""Catalog projection_checkpoint: complete verified source materialization; one DDL."""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE projection_checkpoint (
    company_id BINARY(16) NOT NULL, 
    source_key VARCHAR(120) NOT NULL, 
    source_version BIGINT NOT NULL, 
    snapshot_source_version BIGINT NULL,
    snapshot_id BINARY(16) NULL,
    snapshot_sha256 VARCHAR(64) NULL,
    generated_at DATETIME(6) NULL,
    expires_at DATETIME(6) NULL,
    status VARCHAR(20) NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_projection_checkpoint PRIMARY KEY (id), 
    CONSTRAINT uq_projection_checkpoint_source UNIQUE (tenant_id, company_id, source_key), 
    CONSTRAINT ck_projection_checkpoint_checkpoint_source_version CHECK (source_version >= 0),
        CONSTRAINT ck_projection_checkpoint_checkpoint_snapshot_version CHECK
        (snapshot_source_version IS NULL OR (snapshot_source_version > 0 AND
        snapshot_source_version <= source_version)),
    KEY ix_projection_checkpoint_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE projection_checkpoint")
