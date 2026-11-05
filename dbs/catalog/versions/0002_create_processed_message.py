"""Catalog processed_message: one reviewed literal DDL per direction; content is seeded separately.

Matches the shared platform model. No cross-service foreign key or runtime domain write.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    message_id BINARY(16) NOT NULL,
    processed_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_processed_message PRIMARY KEY (consumer_name, message_id),
    KEY ix_processed_message_processed_at (processed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE processed_message")
