"""Catalog source_event_buffer: complete verified source materialization; one DDL."""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE source_event_buffer (
    source_key VARCHAR(120) NOT NULL, 
    source_version BIGINT NOT NULL, 
    previous_version BIGINT NOT NULL, 
    message_id BINARY(16) NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    payload JSON NOT NULL, 
    generated_at DATETIME(6) NOT NULL, 
    received_at DATETIME(6) NOT NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_source_event_buffer PRIMARY KEY (id), 
    CONSTRAINT uq_source_buffer_version UNIQUE (tenant_id, source_key, source_version), 
    CONSTRAINT uq_source_buffer_message UNIQUE (tenant_id, message_id), 
        CONSTRAINT ck_source_event_buffer_buffer_contiguous_version CHECK (source_version > 1
        AND previous_version = source_version - 1),
    KEY ix_source_buffer_retention (tenant_id, received_at, id),
    KEY ix_source_event_buffer_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE source_event_buffer")
