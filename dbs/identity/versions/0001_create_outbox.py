"""create outbox

Revision ID: 0001
Revises: None

The transactional outbox. First table in the chain because every other table's
state change has to be able to emit an event in its own transaction (CLAUDE.md
invariant 8), so nothing can be written correctly before this exists.

**Why raw DDL rather than `op.create_table`.** Rule 4.8 allows exactly one DDL
statement per revision, and `op.create_table` cannot honour that: SQLAlchemy has
no way to render a secondary index inside a `CREATE TABLE`, so it emits one
`CREATE TABLE` plus one `ALTER TABLE ... ADD INDEX` per index. On MariaDB, with no
transactional DDL, a failure on the second statement leaves the table created and
the revision unstamped — which is the exact desynchronization the rule exists to
prevent. A single `CREATE TABLE` carrying its `KEY` clauses either applies whole
or leaves nothing behind. docs/identity-db-plan.md §1.1.

No values are interpolated into any statement here, so §5.7 has no surface.

Checklist: one DDL statement · no `tenant_id` FK (§1.4) · no NULL inside a UNIQUE
key · DATETIME(6) suffixed `_at` · no ENUM · no FLOAT · downgrade present · no
seed data.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `tenant_id` is nullable and carries no foreign key: platform-level events have
# no tenant, and `tenant` is not created until revision 0007 (§1.4).
#
# `message_id` is UNIQUE so a double-write inside the producing transaction fails
# loudly, rather than delivering the same event twice under two ids. Consumers
# dedupe on it (rule 4.4).
#
# MariaDB implements JSON as LONGTEXT plus a `json_valid` CHECK, so reflection
# reports LONGTEXT for `payload`. That is the storage, not a mismatch.
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
