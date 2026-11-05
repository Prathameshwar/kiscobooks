"""create processed_message

Revision ID: 0002
Revises: 0001

Consumer-side dedupe: redelivery must produce one effect (rule 4.4).

**The primary key is composite, `(consumer_name, message_id)`.** Keyed on
`message_id` alone, the second consumer of a fan-out event finds the row already
present and silently skips the message — data loss that only appears once a second
consumer exists, and by then the missed events are gone.

No `tenant_id`: dedupe is infrastructure and the message may arrive before a
tenant is resolved. On the tenant-filter exemption whitelist with that reason
recorded (docs/identity-schema.md §0.3).

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement · no
NULL inside a UNIQUE key · DATETIME(6) suffixed `_at` · no ENUM · no FLOAT ·
downgrade present · no seed data.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `consumer_name` leads the PK because every lookup supplies it, and because it
# keeps one consumer's rows contiguous in the InnoDB cluster. VARCHAR(120) inside
# a PK is 480 bytes under utf8mb4, well under the 3072-byte DYNAMIC key limit (§1.6).
#
# `ix_processed_message_processed_at` serves the retention sweep, which is the
# only query that does not know a consumer name.
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
