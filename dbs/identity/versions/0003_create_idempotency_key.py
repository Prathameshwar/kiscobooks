"""create idempotency_key

Revision ID: 0003
Revises: 0002

A replayed money-mutating request produces one effect (CLAUDE.md invariant 2).

`request_hash` is present from the start rather than added later, because a key
reused with a *different* body must return 422 and never a replay of the first
response. Without the hash there is nothing to compare, and retrofitting it means
every row already stored is unverifiable.

`tenant_id` leads the unique key, per §1.7: the session filter puts `tenant_id` in
every query, so an index that omits it cannot be used.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement · no
`tenant_id` FK (§1.4) · no NULL inside a UNIQUE key · DATETIME(6) suffixed `_at` ·
`state` is VARCHAR not ENUM · no FLOAT · downgrade present · no seed data.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Key-length check (§1.6), utf8mb4 at 4 bytes per character:
#   uq: 16 + (200 x 4) + (255 x 4) = 1836 bytes — under the 3072-byte limit.
#
# `ix_idempotency_key_tenant_id` is redundant as a prefix of that unique key, but
# it comes from the shared TenantMixin, and the schema must match the models
# exactly or `--autogenerate` proposes it on the next revision for every table.
#
# `state` is VARCHAR + application validation, never MySQL ENUM: altering an ENUM
# rebuilds the table (CLAUDE.md §4).
#
# `expires_at` is indexed for the expiry sweep. Rows are expired, never deleted on
# read: a replay arriving after a delete would be executed a second time.
_CREATE = """
CREATE TABLE idempotency_key (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    key_value VARCHAR(255) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    response_status SMALLINT NULL,
    response_body JSON NULL,
    locked_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    expires_at DATETIME(6) NOT NULL,
    attempt_count INT NOT NULL,
    CONSTRAINT pk_idempotency_key PRIMARY KEY (id),
    CONSTRAINT uq_idempotency_key_tenant_id_endpoint_key_value
        UNIQUE (tenant_id, endpoint, key_value),
    KEY ix_idempotency_key_tenant_id (tenant_id),
    KEY ix_idempotency_key_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE idempotency_key")
