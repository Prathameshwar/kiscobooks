"""Create processed_message; one literal MySQL DDL statement per direction.

The consumer's dedupe key (docs/audit.md §2.2): a broker redelivery of the same
outbox ``message_id`` must not append a second row to the hash chain. The composite PK
``(consumer_name, message_id)`` is deliberate — see ``billing_platform`` platform_models.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
