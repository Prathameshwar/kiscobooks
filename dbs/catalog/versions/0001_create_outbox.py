"""Catalog outbox: one reviewed literal DDL per direction; content is seeded separately.

Matches the shared platform model. No cross-service foreign key or runtime domain write.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE outbox (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BINARY(16) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSON NOT NULL,
    schema_version SMALLINT NOT NULL,
    message_id BINARY(16) NOT NULL,
    trace_id VARCHAR(32) NULL,
    occurred_at DATETIME(6) NOT NULL,
    available_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    attempt_count SMALLINT NOT NULL,
    last_error TEXT NULL,
    CONSTRAINT pk_outbox PRIMARY KEY (id),
    CONSTRAINT uq_outbox_message_id UNIQUE (message_id),
    KEY ix_outbox_published_at_available_at (published_at, available_at),
    KEY ix_outbox_aggregate_type_aggregate_id (aggregate_type, aggregate_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE outbox")
